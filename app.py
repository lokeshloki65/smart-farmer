import os
import base64
import json
import requests
from flask import Flask, request, jsonify, render_template, url_for
from flask_cors import CORS
import cloudinary
import cloudinary.uploader
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta
from dotenv import load_dotenv
# --- NEW --- Import the required Google library
from googleapiclient.discovery import build


load_dotenv()

app = Flask(__name__)
CORS(app)


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
DATA_GOV_API_KEY = os.getenv("DATA_GOV_API_KEY")
FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH")
# --- NEW --- Add these lines to get your Google Search API keys
GOOGLE_CSE_API_KEY = os.getenv("GOOGLE_CSE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")


try:
    cloudinary.config(
        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
        api_key=os.getenv("CLOUDINARY_API_KEY"),
        api_secret=os.getenv("CLOUDINARY_API_SECRET"),
        secure=True
    )
    print("Cloudinary configured successfully.")
except Exception as e:
    print(f"Error configuring Cloudinary: {e}")

try:
    if not FIREBASE_CREDENTIALS_PATH or not os.path.exists(FIREBASE_CREDENTIALS_PATH):
        raise FileNotFoundError(f"Firebase credentials file not found at path: {FIREBASE_CREDENTIALS_PATH}. Check your .env file.")
    cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Firestore initialized successfully.")
except Exception as e:
    print(f"Error initializing Firestore: {e}")
    db = None

try:
    with open('prices.json', 'r', encoding='utf-8') as f:
        all_prices_data = json.load(f)
    print("prices.json loaded successfully.")
except FileNotFoundError:
    all_prices_data = None
    print("WARNING: prices.json not found. The /prices endpoint might have reduced functionality.")
except json.JSONDecodeError:
    all_prices_data = None
    print("ERROR: Could not decode prices.json. Check syntax.")


MODEL_NAME = "gemini-1.5-flash-latest"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"


# --- NEW --- This is the helper function from your friend's code to find an image
def get_image_url_from_google(query):
    """Searches for an image using Google Custom Search API and returns the first result."""
    try:
        if not GOOGLE_CSE_API_KEY or not GOOGLE_CSE_ID:
            print("WARNING: Google CSE API Key or ID is not set. Cannot search for image.")
            return None
            
        service = build("customsearch", "v1", developerKey=GOOGLE_CSE_API_KEY)
        res = service.cse().list(
            q=query,
            cx=GOOGLE_CSE_ID,
            searchType='image',
            num=1,
            safe='high'
        ).execute()

        if 'items' in res and len(res['items']) > 0:
            return res['items'][0]['link']
        else:
            return None
    except Exception as e:
        print(f"ERROR during Google Image Search: {e}")
        return None


@app.route("/")
def index():
    """Renders the main page."""
    return render_template("index.html")

@app.route('/buyer')
def buyer_page():
    """Renders the buyer marketplace page."""
    return render_template('index2.html')

@app.route("/ask-agro-assistant", methods=["POST"])
def ask_agro_assistant():
    """Handles chatbot queries using the Gemini API."""
    try:
        data = request.get_json()
        user_question = data.get("question", "").strip()

        if not user_question:
            return jsonify({"error": "No question provided."}), 400

        system_prompt = """
        You are 'Agro Assistant', a friendly and helpful AI chatbot for a web application designed for farmers.
        Your purpose is to answer user questions about the features of the Agro Assistant application.
        Your answers should be concise, helpful, and in a conversational tone.

        Here is a summary of the application's features:
        - *Crop Disease Prediction*: Users can upload an image of a crop leaf, and the AI will identify if it has a disease and suggest remedies.
        - *Weather Forecast*: Provides real-time weather updates for any city or the user's current location. It also shows weather in nearby major cities.
        - *Market Prices*: Tracks the latest prices of vegetables in local markets like Coimbatore and Salem.
        - *AI Planner*: Gives intelligent suggestions for crops to plant based on land area and season (Kharif, Rabi, Summer). It provides estimated costs and farming tips.
        - *Buy/Sell Marketplace*: A platform where farmers can list their products (vegetables, fruits, grains) for sale, and buyers can browse and purchase them.
        - *Agri News*: Shows the latest agricultural news from India and around the world.
        - *Agri Loan Application*: A step-by-step form that allows farmers to apply for loans by uploading PAN Card, bank statement, and personal details. After checking eligibility, users can submit a final application. The interest rate is 1% per annum with monthly repayment terms.
        - *About Us*: Information about the app's mission and the development team (Lokesh, Sarjan, Nishanth, Karthick). Our Mentors ...Dr.P.Thangavelu (Principal) and Dr.R.Senthil Kumar (HOD)

        Based on this information, please answer the user's question. If the question is unrelated to the Agro Assistant application or its features, politely state that you can only answer questions about the application.
        """

        gemini_payload = {
            "contents": [
                {
                    "parts": [
                        {"text": system_prompt},
                        {"text": f"User's question: {user_question}"}
                    ]
                }
            ]
        }

        response = requests.post(GEMINI_API_URL, json=gemini_payload, timeout=45)
        response.raise_for_status()

        result_text = response.json()['candidates'][0]['content']['parts'][0]['text']

        return jsonify({"answer": result_text})

    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Could not connect to the AI service: {e}"}), 503
    except Exception as e:
        print(f"CHATBOT ERROR: {e}")
        return jsonify({"error": f"An unexpected error occurred: {e}"}), 500

@app.route("/upload-item-image", methods=["POST"])
def upload_item_image():
    """Handles image uploads for marketplace items to Cloudinary."""
    if 'item_image' not in request.files:
        return jsonify({"error": "No 'item_image' file part"}), 400
    file_to_upload = request.files['item_image']
    if file_to_upload.filename == '':
        return jsonify({"error": "No file selected"}), 400
    try:
        upload_result = cloudinary.uploader.upload(file_to_upload, folder="agri_assistant_items")
        return jsonify({"imageUrl": upload_result.get('secure_url')})
    except Exception as e:
        print(f"CLOUDINARY UPLOAD ERROR: {e}")
        return jsonify({"error": f"Failed to upload image: {e}"}), 500
@app.route('/upload-profile-image', methods=['POST'])
def upload_profile_image():
    """Handles profile image uploads to Cloudinary with debugging."""
    print("INFO: Received request for /upload-profile-image") 
    if 'profile_image' not in request.files:
        print("ERROR: 'profile_image' not in request.files") 
        return jsonify({'error': 'No file part in the request'}), 400
    
    file = request.files['profile_image']

    if file.filename == '':
        print("ERROR: No file selected by user")
        return jsonify({'error': 'No selected file'}), 400

    if file:
        try:
            print("INFO: Uploading file to Cloudinary...")
            # Upload the file to Cloudinary in a specific folder for profiles
            upload_result = cloudinary.uploader.upload(file, folder="agro_assistant_profiles")
            
            # Get the secure URL of the uploaded image
            secure_url = upload_result.get('secure_url')
            print(f"SUCCESS: Cloudinary URL is {secure_url}")

            # Return the URL to the frontend
            return jsonify({'message': 'Image uploaded successfully', 'secure_url': secure_url}), 200

        except Exception as e:
            print(f"CLOUDINARY PROFILE UPLOAD ERROR: {e}") 
            return jsonify({'error': str(e)}), 500

    return jsonify({'error': 'An unknown error occurred'}), 500

@app.route('/add-item', methods=['POST'])
def add_item():
    """Adds a new product item to the Firestore database."""
    if not db:
        return jsonify({"error": "Database not initialized"}), 500
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data received in request"}), 400
        db.collection('products').add(data)
        return jsonify({"success": True, "message": "Item added successfully"}), 201
    except Exception as e:
        print(f"ERROR in /add-item endpoint: {e}")
        return jsonify({"error": f"Failed to add item: {e}"}), 500

@app.route('/get-items', methods=['GET'])
def get_items():
    """Retrieves all product items from the Firestore database."""
    if not db:
        return jsonify({"error": "Database not initialized"}), 500
    try:
        products_ref = db.collection('products').stream()
        products_list = []
        for doc in products_ref:
            product_data = doc.to_dict()
            product_data['id'] = doc.id
            products_list.append(product_data)
        return jsonify(products_list)
    except Exception as e:
        return jsonify({"error": f"Failed to get items: {e}"}), 500

@app.route("/agri-news", methods=["GET"])
def agri_news():
    if not NEWS_API_KEY:
        return jsonify({"error": "News API key is not configured."}), 500

    search_query = ('("agriculture" AND "india") OR '
                    '("farming" AND "india") OR '
                    '("indian farmers") OR '
                    '("crops price" AND "india") OR '
                    '("horticulture" AND "india") OR '
                    '("monsoon" AND "crops") OR '
                    '("fertilizer policy" AND "india")')

    url = (f"https://newsapi.org/v2/everything?"
           f"q={search_query}"
           f"&language=en"
           f"&sortBy=publishedAt"
           f"&apiKey={NEWS_API_KEY}")

    try:
        response = requests.get(url)
        response.raise_for_status()
        news_data = response.json()
        filtered_articles = [article for article in news_data.get("articles", []) if article.get("title") != "[Removed]"]
        return jsonify({"articles": filtered_articles[:20]})
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Could not retrieve news data: {e}"}), 502
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {e}"}), 500

@app.route("/predict", methods=["POST"])
def predict():
    """Analyzes a leaf image and returns a comprehensive farming guide."""
    if 'leaf' not in request.files:
        return jsonify({"error": "No 'leaf' file part in the request"}), 400

    file = request.files['leaf']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    try:
        image_bytes = file.read()
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        prompt_text = """
        You are an expert agricultural scientist for Indian farming conditions. Analyze the provided plant leaf image and generate a complete, practical farming guide.
        Your entire output must be a single block of human-readable plain text. Do NOT use JSON or markdown formatting.
        Use the exact headings provided below, each on a new line, to structure your response.

        ### DISEASE ANALYSIS ###
        - Identify the disease on the leaf. If healthy, state "The leaf appears to be healthy."
        - Provide 3 clear, step-by-step remedies for the disease.

        ### HEALTHY LEAF TIPS ###
        - If the leaf is healthy, provide 3 practical care tips for the plant. If it is diseased, skip this section entirely.
        
        ### SOIL SUITABILITY ###
        - Describe the ideal soil type for this plant (e.g., Loamy, Sandy, Clay).
        - State the optimal soil pH range (e.g., 6.0-7.0).

        ### WATERING GUIDE ###
        - Provide a clear watering schedule (e.g., "Water deeply once a week, more in summer.").
        - Mention a simple method to check for soil moisture.
        
        ### FERTILIZER RECOMMENDATION ###
        - Suggest a suitable NPK ratio (e.g., 10-10-10) or type of organic manure.
        - Specify when and how often to apply the fertilizer.
        
        ### PEST CONTROL ###
        - List 2-3 common pests that affect this plant.
        - For each pest, suggest one organic and one chemical control method.
        
        ### PLANTING GUIDE ###
        - Recommend the ideal spacing between individual plants.
        - Suggest the proper planting depth for seeds or saplings.
        """

        gemini_payload = {
            "contents": [{"parts": [{"inlineData": {"mime_type": "image/jpeg", "data": image_b64}}, {"text": prompt_text}]}]
        }

        response = requests.post(GEMINI_API_URL, json=gemini_payload, timeout=60)
        response.raise_for_status()

        gemini_response_data = response.json()
        if 'candidates' not in gemini_response_data or not gemini_response_data['candidates']:
            print(f"GEMINI API ERROR: No candidates returned. Response: {gemini_response_data}")
            return jsonify({"error": "Gemini API did not provide a valid analysis."}), 500

        prediction_report_text = gemini_response_data['candidates'][0]['content']['parts'][0]['text']
        return jsonify({"prediction_text": prediction_report_text})

    except requests.exceptions.RequestException as e:
        print(f"NETWORK/REQUEST ERROR: {e}")
        return jsonify({"error": f"Failed to connect to the prediction service: {e}"}), 502
    except Exception as e:
        print(f"PREDICTION ERROR: {e}")
        return jsonify({"error": f"An unexpected error occurred on the server: {e}"}), 500

@app.route("/weather", methods=["GET"])
def weather():
    """Fetches comprehensive weather data from OpenWeatherMap OneCall API."""
    lat = request.args.get("lat")
    lon = request.args.get("lon")
    city_name_query = request.args.get("city")

    if not OPENWEATHER_API_KEY:
        return jsonify({"error": "Weather API key not configured"}), 500
    
    final_city_name = city_name_query

    try:
        if city_name_query:
            geo_url = f"http://api.openweathermap.org/geo/1.0/direct?q={city_name_query}&limit=1&appid={OPENWEATHER_API_KEY}"
            geo_response = requests.get(geo_url)
            geo_response.raise_for_status()
            geo_data = geo_response.json()
            if not geo_data:
                return jsonify({"error": f"City '{city_name_query}' not found. Please check spelling."}), 404
            lat = geo_data[0]['lat']
            lon = geo_data[0]['lon']
        
        elif lat and lon:
            # THIS IS THE FIX: Reverse geocode to get city name from lat/lon
            reverse_geo_url = f"http://api.openweathermap.org/geo/1.0/reverse?lat={lat}&lon={lon}&limit=1&appid={OPENWEATHER_API_KEY}"
            reverse_geo_response = requests.get(reverse_geo_url)
            reverse_geo_response.raise_for_status()
            reverse_geo_data = reverse_geo_response.json()
            if reverse_geo_data:
                final_city_name = reverse_geo_data[0]['name']

        if not lat or not lon:
            return jsonify({"error": "City name or latitude/longitude are required"}), 400

        # Fetch detailed weather data
        one_call_url = f"https://api.openweathermap.org/data/3.0/onecall?lat={lat}&lon={lon}&exclude=minutely&units=metric&appid={OPENWEATHER_API_KEY}"
        weather_response = requests.get(one_call_url)
        weather_response.raise_for_status()
        weather_data = weather_response.json()

        # Fetch air pollution data
        air_pollution_url = f"http://api.openweathermap.org/data/2.5/air_pollution?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}"
        air_response = requests.get(air_pollution_url)
        air_response.raise_for_status()
        air_data = air_response.json()

        # Combine the data
        weather_data['air_quality'] = air_data.get('list', [{}])[0]
        weather_data['city_name'] = final_city_name or weather_data.get('timezone', 'Unknown').split('/')[-1].replace('_', ' ')

        return jsonify(weather_data)

    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Could not connect to weather service: {e}"}), 502
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {e}"}), 500


# ***************************************************************
# ******** NEW SECTION FOR WEATHER HISTORY ADDED BELOW ********
# ***************************************************************

@app.route("/weather-history", methods=["GET"])
def weather_history():
    """Fetches historical weather data for the last 7 days."""
    lat = request.args.get("lat")
    lon = request.args.get("lon")

    if not lat or not lon:
        return jsonify({"error": "Latitude and longitude are required"}), 400

    if not OPENWEATHER_API_KEY:
        return jsonify({"error": "Weather API key not configured"}), 500

    historical_data = []
    today = datetime.utcnow()

    try:
        # Loop to get data for each of the last 7 days
        for i in range(1, 8):
            # Calculate the timestamp for the past day
            past_date = today - timedelta(days=i)
            timestamp = int(past_date.timestamp())
            
            # Call the OpenWeatherMap Timemachine API
            history_url = f"https://api.openweathermap.org/data/3.0/onecall/timemachine?lat={lat}&lon={lon}&dt={timestamp}&units=metric&appid={OPENWEATHER_API_KEY}"
            
            response = requests.get(history_url)
            response.raise_for_status()
            day_data = response.json()

            # The API returns data for the whole day, we'll process the first entry as representative
            if day_data and day_data.get('data'):
                # We need to find the max and min temp from the hourly data provided for that day
                hourly_temps = [hour['temp'] for hour in day_data['data'][0]['hourly']]
                max_temp = max(hourly_temps) if hourly_temps else None
                min_temp = min(hourly_temps) if hourly_temps else None
                
                # Extract daily summary
                daily_summary = day_data['data'][0]
                
                historical_data.append({
                    "date": past_date.strftime('%Y-%m-%d'),
                    "temp_max": max_temp,
                    "temp_min": min_temp,
                    "condition": daily_summary['weather'][0]['main'],
                    "icon": daily_summary['weather'][0]['icon'],
                    "humidity": daily_summary['humidity'],
                    "wind_speed": daily_summary['wind_speed']
                })

        # The data is from newest to oldest, reverse it for chronological order
        return jsonify({"history": historical_data[::-1]})

    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Could not connect to weather history service: {e}"}), 502
    except Exception as e:
        print(f"WEATHER HISTORY ERROR: {e}")
        return jsonify({"error": f"An unexpected error occurred while fetching history: {e}"}), 500


@app.route("/prices", methods=["GET"])
def prices():
    """Fetches vegetable prices using a smart, two-step approach."""
    location_query = request.args.get('location', '').strip()
    vegetable_query = request.args.get('vegetable', '').strip()

    if not location_query or not vegetable_query:
        return jsonify({"error": "Location and vegetable parameters are required."}), 400

    try:
        print(f"INFO: Attempting to fetch real-time price for {vegetable_query} in {location_query}...")
        resource_id = "9ef84268-d588-465a-a308-a864a43d0070"
        gov_api_url = (f"https://api.data.gov.in/resource/{resource_id}?"
                       f"api-key={DATA_GOV_API_KEY}&format=json&"
                       f"filters[market]={location_query.title()}&"
                       f"filters[commodity]={vegetable_query.title()}")

        response = requests.get(gov_api_url, timeout=20)

        if response.status_code == 200:
            data = response.json()
            records = data.get('records', [])
            if records:
                print("SUCCESS: Found real-time price.")
                latest_record = records[-1]
                found_price = latest_record.get('modal_price', 'N/A')
                result = {
                    "prices": [{
                        "name": latest_record.get('commodity'),
                        "location": latest_record.get('market'),
                        "price": f"₹ {found_price} per Quintal"
                    }]
                }
                return jsonify(result)
    except requests.exceptions.RequestException as e:
        print(f"WARNING: Real-time API request failed: {e}. Proceeding to AI fallback.")
        pass

    try:
        print("INFO: Real-time price not found. Using Gemini AI for estimation...")
        prompt = f"""
        As an agricultural market expert, provide a single, average estimated market price for '{vegetable_query}' in the '{location_query}' region of India.
        Your entire response MUST be only a single, valid JSON object with no markdown or any other text.
        Use this exact structure: {{"estimated_price": "Approx. ₹Z per Kg"}}
        """
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"response_mime_type": "application/json"}
        }
        gemini_response = requests.post(GEMINI_API_URL, json=payload, timeout=45)
        gemini_response.raise_for_status()

        ai_data = gemini_response.json()
        cleaned_text = ai_data['candidates'][0]['content']['parts'][0]['text']
        price_data = json.loads(cleaned_text)
        estimated_price = price_data.get("estimated_price", "Could not estimate.")

        print(f"SUCCESS: AI estimated price: {estimated_price}")
        result = {
            "prices": [{
                "name": vegetable_query.title(),
                "location": location_query.title(),
                "price": f"{estimated_price} (Estimated)"
            }]
        }
        return jsonify(result)
    except Exception as e:
        print(f"ERROR: Both real-time API and AI fallback failed. Error: {e}")
        return jsonify({"error": f"Sorry, could not find or estimate the price for {vegetable_query}."}), 500

@app.route("/vegetable-info", methods=["GET"])
def vegetable_info():
    """Fetches detailed information about a vegetable using the Gemini API."""
    vegetable_name = request.args.get('name', '').strip()
    if not vegetable_name:
        return jsonify({"error": "Vegetable name is required."}), 400

    try:
        prompt = f"""
        Provide a detailed guide for the vegetable '{vegetable_name}'.
        Your entire response MUST be a single, valid JSON object with no markdown or any other text.
        Use this exact structure:
        {{
          "name": "{vegetable_name.title()}",
          "image_search_term": "A simple search term to find a high-quality photo, e.g., 'Fresh {vegetable_name}'",
          "history": "A brief, interesting history of the vegetable's origin and its journey to India (2-3 sentences).",
          "cultivation": {{
            "soil": "Ideal soil type and pH range for this vegetable.",
            "water": "Watering requirements (e.g., frequency, amount).",
            "climate": "Suitable climate conditions (e.g., temperature range, sunlight)."
          }},
          "nutrition": [
            {{"nutrient": "Calories", "value": "Approx. value per 100g"}},
            {{"nutrient": "Vitamin C", "value": "Approx. value or % of Daily Value"}},
            {{"nutrient": "Potassium", "value": "Approx. value per 100g"}},
            {{"nutrient": "Fiber", "value": "Approx. value per 100g"}}
          ]
        }}
        """

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"response_mime_type": "application/json"}
        }

        gemini_response = requests.post(GEMINI_API_URL, json=payload, timeout=45)
        gemini_response.raise_for_status()

        ai_data_text = gemini_response.json()['candidates'][0]['content']['parts'][0]['text']
        veg_data = json.loads(ai_data_text)
        
        # --- MODIFIED SECTION ---
        # This part now uses the Google Search function to find a reliable image.
        search_term = veg_data.get("image_search_term", vegetable_name)
        image_url = get_image_url_from_google(search_term)
        
        # If Google search fails, it falls back to the old Unsplash link.
        veg_data["image_url"] = image_url or f"https://source.unsplash.com/400x400/?{vegetable_name.replace(' ', '+')}"

        return jsonify(veg_data)

    except Exception as e:
        print(f"VEGETABLE INFO ERROR: {e}")
        return jsonify({"error": f"Could not retrieve details for {vegetable_name}."}), 500


def get_current_indian_season():
    """Determines the current Indian agricultural season."""
    current_month = datetime.now().month
    if 6 <= current_month <= 10:
        return "Kharif (Monsoon Crop)"
    elif 11 <= current_month or current_month <= 3:
        return "Rabi (Winter Crop)"
    else:
        return "Zaid (Summer Crop)"

@app.route("/planner", methods=["GET"])
def planner():
    """Generates a detailed, location-specific farming plan."""
    crop = request.args.get("crop", "").strip()
    area = request.args.get("area", "").strip()
    location = request.args.get("location", "").strip()

    if not all([crop, area, location]):
        return jsonify({"error": "Crop, area, and location are required"}), 400

    current_season = get_current_indian_season()
    prompt = f"""
    As a master agricultural planner for India, create a highly detailed and practical farming plan.

    **Farmer's Request:**
    - **Crop:** {crop}
    - **Land Area:** {area} acres
    - **Location:** Near {location}, India
    - **Current Agricultural Season:** {current_season}

    **Your Task:**
    Generate a comprehensive plan. Your entire response MUST be a single, valid JSON object with no markdown or other text.
    Use this exact nested structure:
    {{
      "plan_summary": {{
        "title": "A catchy title for the plan, e.g., 'High-Yield {crop} Farming Plan for {area} Acres'",
        "suitability": "A brief sentence on how suitable {crop} is for {location} in the {current_season}."
      }},
      "cost_and_profit_estimation": {{
        "total_estimated_cost": "Provide a single, total estimated cost for the entire {area} acres for one crop cycle. Example: 'Approx. ₹90,000 - ₹1,10,000 total'.",
        "cost_breakdown": [
          {{"item": "Seeds/Saplings", "cost": "e.g., ₹15,000"}},
          {{"item": "Land Preparation", "cost": "e.g., ₹10,000"}},
          {{"item": "Fertilizers & Manure", "cost": "e.g., ₹25,000"}},
          {{"item": "Pesticides/Insecticides", "cost": "e.g., ₹10,000"}},
          {{"item": "Labor (Planting, Weeding, Harvesting)", "cost": "e.g., ₹30,000"}},
          {{"item": "Irrigation & Other", "cost": "e.g., ₹10,000"}}
        ],
        "estimated_yield": "An estimated total yield from the {area} acres, e.g., 'Approx. 20-25 Tonnes'.",
        "estimated_profit": "A potential profit estimation after selling the yield, e.g., 'Approx. ₹1,50,000 - ₹2,00,000'."
      }},
      "step_by_step_guide": {{
        "timeline_weeks": "Estimated duration of the crop cycle in weeks, e.g., '12-14 Weeks'.",
        "steps": [
          {{"stage": "Week 1-2: Preparation", "action": "Detailed actions for land preparation, soil testing, and manure application."}},
          {{"stage": "Week 3: Planting", "action": "Instructions on planting technique, spacing, and initial irrigation."}},
          {{"stage": "Week 4-8: Growth & Care", "action": "Guidance on fertilization schedule, weeding, and pest monitoring."}},
          {{"stage": "Week 9-11: Flowering & Fruiting", "action": "Specific care needed during this critical stage, like nutrient management."}},
          {{"stage": "Week 12-14: Harvesting", "action": "Instructions on how to harvest properly to maximize yield and quality."}}
        ]
      }}
    }}
    """
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json"}
    }
    try:
        response = requests.post(GEMINI_API_URL, json=payload, timeout=60)
        response.raise_for_status()
        plan_data_string = response.json()['candidates'][0]['content']['parts'][0]['text']
        return jsonify(json.loads(plan_data_string))
    except Exception as e:
        print(f"PLANNER ERROR: {e}")
        return jsonify({"error": f"Failed to generate plan: {e}"}), 500

if __name__ == "__main__":
    print("Starting Flask server...")
    app.run(host='0.0.0.0', port=5000, debug=True)