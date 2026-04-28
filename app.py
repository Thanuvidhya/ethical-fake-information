import os, requests, pytesseract
from flask import Flask, render_template, request
from PIL import Image
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import re

# Set Tesseract path (uncomment and modify if needed)
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

load_dotenv()
app = Flask(__name__)

SYSTEM_PROMPT = '''You are a fake news detector. Analyze the given claim and provide:

FIRST LINE: REAL or FAKE (choose only one)

If FAKE:
- Rewrite it as truthful news in 1-2 sentences
- Add "Changes Made:" section explaining what was corrected and why

If REAL:
- Confirm it's accurate in 1-2 sentences
- Add "Verification:" section explaining why it's confirmed real

Be decisive and consistent. For fake news, clearly explain the corrections needed to make it truthful.'''

CAPTION_PROMPT = '''You are an Ethical Image Caption Recommendation Engine.

Your responsibility is to recommend a suitable caption for a social media post
based ONLY on the visual content of the given image.

Rules:
- Generate a human-friendly caption inspired by the image
- The caption must be ethical, neutral, and socially responsible
- Do NOT assume identities, names, locations, events, or emotions
- Do NOT invent stories or exaggerate situations
- Do NOT include misinformation, stereotypes, or sensitive claims
- Keep caption descriptive but suitable for public posting
- Include relevant visual details that make the caption more engaging

Output format (follow strictly):

Recommended Caption:
"<caption text>"

The caption should be 1-2 descriptive sentences that capture the essence of the scene while remaining neutral and appropriate.'''

CONTENT_ANALYSIS_PROMPT = '''You are an Ethical Content Analysis, Moderation, and Recommendation System.

When an image is provided, your tasks are:

1. Analyze the image and classify it into ONE category only:
   - Safe content
   - Child-sensitive content
   - Adult or explicit content
   - Violent or disturbing content
   - Sensitive but non-explicit content

2. Based on the classification:
   - If Safe content:
     Generate an ethical, respectful, and non-misleading caption suitable for social media.
   - If Child-sensitive, Adult, or Violent content:
     Do NOT generate a caption.
     Clearly state that caption recommendation is restricted due to ethical and safety concerns.
   - If Sensitive but non-explicit content:
     Generate a neutral, awareness-based caption that avoids harm or encouragement.

3. Do not extract text from the image.
4. Do not make assumptions about identity, intent, or background.

Output format (follow strictly):
Image Category: <category>
Response: <caption OR restriction message>'''

TEXT_SANITIZATION_PROMPT = '''You are an Ethical Text Rewriting & Content Sanitization System.

When text content (news, post, caption, comment, or URL-extracted text) is provided, your tasks are:

1. Analyze the text for:
   - Fake or misleading information
   - Hate speech, abusive words, or profanity
   - Harmful, unethical, or exaggerated claims

2. If problematic content is detected:
   - Rewrite the text into a factual, ethical, and respectful version.
   - Replace bad or abusive words with neutral alternatives.
   - Preserve the original meaning without spreading harm.

3. If the text is already ethical and factual:
   - Clearly state that no rewriting is required.

4. Do not add new information or opinions.

Output format (follow strictly):
Content Status: <Ethical / Rewritten>
Original Issue: <brief issue>
Ethical Version: <corrected text>'''

def fetch_url_content(url):
    """Extract text content from a URL"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        # Try with different approaches
        for attempt in range(3):
            try:
                response = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Remove script and style elements
                for script in soup(["script", "style"]):
                    script.decompose()
                
                # Get text from common content areas
                title = soup.find('title')
                title_text = title.get_text().strip() if title else ""
                
                # Try to find main content
                content_selectors = [
                    'article', 'main', '.content', '.post-content', 
                    '.entry-content', '.article-content', '[role="main"]',
                    '.post-body', '.article-body', '.story-body'
                ]
                
                content_text = ""
                for selector in content_selectors:
                    content = soup.select_one(selector)
                    if content:
                        content_text = content.get_text()
                        break
                
                # Fallback to body if no main content found
                if not content_text:
                    content_text = soup.get_text()
                
                # Clean up text
                text = f"{title_text}\n\n{content_text}"
                text = re.sub(r'\s+', ' ', text)  # Remove extra whitespace
                text = text.strip()
                
                # Limit to first 2000 characters to avoid token limits
                if len(text) > 2000:
                    text = text[:2000] + "..."
                    
                return text
                
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 403:
                    # Try with a simpler user agent for 403 errors
                    headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    continue
                else:
                    raise e
                    
    except Exception as e:
        return f"Error fetching URL: {str(e)}. Some websites block automated access. Try a different URL or copy-paste the content directly."

def call_api(api_key, api_url, model, content):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content}
        ]
    }
    try:
        r = requests.post(api_url, headers=headers, json=payload, timeout=30)
        response_data = r.json()
        
        # Debug: Print response to see what's actually returned
        print(f"API Response Status: {r.status_code}")
        print(f"API Response: {response_data}")
        
        if "choices" in response_data:
            return response_data["choices"][0]["message"]["content"]
        else:
            return f"API Error: {response_data}"
    except Exception as e:
        return f"API Call Failed: {str(e)}"

@app.route("/caption", methods=["GET", "POST"])
def caption_generator():
    caption_result = ""
    
    if request.method == "POST":
        image = request.files.get("caption_image")
        
        if image:
            try:
                # Convert image to base64 for API
                import base64
                from io import BytesIO
                
                img = Image.open(image)
                # Convert RGBA to RGB for JPEG compatibility
                if img.mode == 'RGBA':
                    img = img.convert('RGB')
                buffered = BytesIO()
                img.save(buffered, format="JPEG")
                img_base64 = base64.b64encode(buffered.getvalue()).decode()
                
                # Get caption from API
                caption = call_vision_api(img_base64)
                caption_result = caption
                
            except Exception as e:
                caption_result = f"Error generating caption: {str(e)}"
        else:
            caption_result = "Please upload an image to generate a caption."
    
    return render_template("caption.html", result=caption_result)

def call_vision_api(image_base64):
    """Call vision API for image analysis"""
    # Using OpenRouter with vision model
    headers = {
        "Authorization": f"Bearer {os.getenv('API1_KEY')}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "openai/gpt-4o",  # GPT-4o supports vision
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": CAPTION_PROMPT
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 100
    }
    
    try:
        r = requests.post("https://openrouter.ai/api/v1/chat/completions", 
                        headers=headers, json=payload, timeout=30)
        response_data = r.json()
        
        if "choices" in response_data:
            return response_data["choices"][0]["message"]["content"]
        else:
            return f"Vision API Error: {response_data}"
    except Exception as e:
        return f"Vision API Call Failed: {str(e)}"

@app.route("/url", methods=["GET", "POST"])
def url_detector():
    result = ""
    url_content = ""
    
    if request.method == "POST":
        url = request.form.get("url", "")
        
        if url:
            url_content = fetch_url_content(url)
            if url_content and not url_content.startswith("Error"):
                # Analyze the URL content
                outputs = []
                valid_results = []
                
                for i in ["2"]:  # Only use API2 for now
                    try:
                        api_result = call_api(
                            os.getenv(f"API{i}_KEY"),
                            os.getenv(f"API{i}_URL"),
                            os.getenv(f"API{i}_MODEL"),
                            url_content
                        )
                        if not api_result.startswith("API Error") and not api_result.startswith("API Call Failed"):
                            outputs.append(f"API{i}: {api_result}")
                            valid_results.append(api_result)
                        else:
                            outputs.append(f"API{i} Error: {api_result}")
                    except Exception as e:
                        outputs.append(f"API{i} Failed: {str(e)}")
                
                # Get result from API2 (only one API running)
                if valid_results:
                    result = valid_results[0]  # Use API2 result directly
                else:
                    result = "API failed. Please check your API key."
            else:
                result = f"URL Error: Unable to fetch content from the URL. The website may be blocking access or the URL is invalid. Please try a different URL or copy-paste the content directly."
        else:
            result = "Please enter a URL to analyze."
    
    return render_template("url.html", result=result, url_content=url_content)

@app.route("/image", methods=["GET", "POST"])
def image_detector():
    result = ""
    extracted_text = ""
    uploaded_image = None
    
    if request.method == "POST":
        image = request.files.get("image")
        
        if image:
            try:
                # Convert image to base64 for display
                import base64
                from io import BytesIO
                
                img = Image.open(image)
                # Convert RGBA to RGB for JPEG compatibility
                if img.mode == 'RGBA':
                    img = img.convert('RGB')
                buffered = BytesIO()
                img.save(buffered, format="JPEG")
                img_base64 = base64.b64encode(buffered.getvalue()).decode()
                uploaded_image = f"data:image/jpeg;base64,{img_base64}"
                
                # Extract text using OCR
                extracted_text = pytesseract.image_to_string(img)
                
                if extracted_text.strip():
                    # Analyze the extracted text
                    outputs = []
                    valid_results = []
                    
                    for i in ["2"]:  # Only use API2 for now
                        try:
                            api_result = call_api(
                                os.getenv(f"API{i}_KEY"),
                                os.getenv(f"API{i}_URL"),
                                os.getenv(f"API{i}_MODEL"),
                                extracted_text
                            )
                            if not api_result.startswith("API Error") and not api_result.startswith("API Call Failed"):
                                outputs.append(f"API{i}: {api_result}")
                                valid_results.append(api_result)
                            else:
                                outputs.append(f"API{i} Error: {api_result}")
                        except Exception as e:
                            outputs.append(f"API{i} Failed: {str(e)}")
                    
                    # Get result from API2 (only one API running)
                    if valid_results:
                        result = valid_results[0]  # Use API2 result directly
                    else:
                        result = "API failed. Please check your API key."
                else:
                    result = "No text could be extracted from the image. Please try a clearer image."
                    
            except Exception as e:
                result = f"Error processing image: {str(e)}"
        else:
            result = "Please upload an image to analyze."
    
    return render_template("image.html", result=result, extracted=extracted_text, uploaded_image=uploaded_image)

@app.route("/content-analysis", methods=["GET", "POST"])
def content_analysis():
    result = ""
    uploaded_image = None
    
    if request.method == "POST":
        image = request.files.get("analysis_image")
        
        if image:
            try:
                # Convert image to base64 for API
                import base64
                from io import BytesIO
                
                img = Image.open(image)
                # Convert RGBA to RGB for JPEG compatibility
                if img.mode == 'RGBA':
                    img = img.convert('RGB')
                buffered = BytesIO()
                img.save(buffered, format="JPEG")
                img_base64 = base64.b64encode(buffered.getvalue()).decode()
                uploaded_image = f"data:image/jpeg;base64,{img_base64}"
                
                # Analyze content using vision API
                analysis = call_content_analysis_api(img_base64)
                result = analysis
                
            except Exception as e:
                result = f"Error analyzing image: {str(e)}"
        else:
            result = "Please upload an image to analyze."
    
    return render_template("content-analysis.html", result=result, uploaded_image=uploaded_image)

@app.route("/text-sanitization", methods=["GET", "POST"])
def text_sanitization():
    result = ""
    
    if request.method == "POST":
        text = request.form.get("text", "")
        
        if text.strip():
            try:
                # Analyze and sanitize text
                analysis = call_text_sanitization_api(text)
                result = analysis
            except Exception as e:
                result = f"Error processing text: {str(e)}"
        else:
            result = "Please provide text to analyze and sanitize."
    
    return render_template("text-sanitization.html", result=result)

def call_content_analysis_api(image_base64):
    """Call vision API for content analysis"""
    headers = {
        "Authorization": f"Bearer {os.getenv('API1_KEY')}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "openai/gpt-4o",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": CONTENT_ANALYSIS_PROMPT
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 150
    }
    
    try:
        r = requests.post("https://openrouter.ai/api/v1/chat/completions", 
                        headers=headers, json=payload, timeout=30)
        response_data = r.json()
        
        if "choices" in response_data:
            return response_data["choices"][0]["message"]["content"]
        else:
            return f"Content Analysis Error: {response_data}"
    except Exception as e:
        return f"Content Analysis Failed: {str(e)}"

def call_text_sanitization_api(text):
    """Call API for text sanitization"""
    headers = {
        "Authorization": f"Bearer {os.getenv('API1_KEY')}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "openai/gpt-4o-mini",
        "messages": [
            {
                "role": "system",
                "content": TEXT_SANITIZATION_PROMPT
            },
            {
                "role": "user",
                "content": text
            }
        ],
        "max_tokens": 500
    }
    
    try:
        r = requests.post("https://openrouter.ai/api/v1/chat/completions", 
                        headers=headers, json=payload, timeout=30)
        response_data = r.json()
        
        if "choices" in response_data:
            return response_data["choices"][0]["message"]["content"]
        else:
            return f"Text Sanitization Error: {response_data}"
    except Exception as e:
        return f"Text Sanitization Failed: {str(e)}"

@app.route("/", methods=["GET", "POST"])
def index():
    result = ""
    
    if request.method == "POST":
        text = request.form.get("news", "")
        
        if text.strip():
            outputs = []
            valid_results = []
            
            for i in ["2"]:  # Only use API2 for now
                try:
                    api_result = call_api(
                        os.getenv(f"API{i}_KEY"),
                        os.getenv(f"API{i}_URL"),
                        os.getenv(f"API{i}_MODEL"),
                        text
                    )
                    if not api_result.startswith("API Error") and not api_result.startswith("API Call Failed"):
                        outputs.append(f"API{i}: {api_result}")
                        valid_results.append(api_result)
                    else:
                        outputs.append(f"API{i} Error: {api_result}")
                except Exception as e:
                    outputs.append(f"API{i} Failed: {str(e)}")
            
            # Get result from API2 (only one API running)
            if valid_results:
                result = valid_results[0]  # Use API2 result directly
            else:
                result = "API failed. Please check your API key."
        else:
            result = "Please provide text to analyze."
    
    return render_template("index.html", result=result)

if __name__ == "__main__":
    app.run(debug=True)