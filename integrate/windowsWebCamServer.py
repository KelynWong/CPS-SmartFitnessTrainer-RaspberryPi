import os
from flask import Flask, jsonify, request
import subprocess
import threading
import signal
import time
import requests
import pyttsx3
from flask_swagger_ui import get_swaggerui_blueprint

# OAuth 2.0 dependencies
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dotenv import load_dotenv
from pyngrok import ngrok 

app = Flask(__name__)
ffmpeg_process = None
pushup_process = None

# Load environment variables from .env file
load_dotenv()

# Initialize the TTS engine
tts_engine = pyttsx3.init()

def speak_text(text):
    # Run the TTS engine in a separate thread to avoid blocking the response
    def speak():
        tts_engine.say(text)
        tts_engine.runAndWait()

    # Start the speak function in a separate thread
    threading.Thread(target=speak).start()

# youtube live variables
youtube_stream_key = os.getenv("YOUTUBE_STREAM_KEY")
youtube_channel_id = os.getenv("YOUTUBE_CHANNEL_ID")

# OAuth 2.0 setup
CLIENT_SECRETS_FILE = os.getenv("CLIENT_SECRETS_FILE")
TOKEN_FILE = os.getenv("TOKEN_FILE")
SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]

# supabase variables
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_API_KEY = os.getenv("SUPABASE_API_KEY")

SUPABASE_WORKOUT_TABLE = "userWorkouts"

# FFmpeg command
ffmpeg_command = [
    'C:\\Program Files\\ffmpeg-7.0.2-essentials_build\\bin\\ffmpeg',  # change path of ffmpeg here if needed
    '-re',  # Read input file at native frame rate
    '-i', 'output_pushup.mp4',  # The output file from push_up.py
    "-s", "1920x1080",
    "-r", "30",
    "-vcodec", "libx264",
    "-preset", "veryfast",
    "-g", "60",  # Set keyframe interval (for 30 fps, 2 seconds interval = 60 frames)
    "-acodec", "aac",
    "-ar", "44100",
    "-b:a", "128k",
    "-b:v", "6800k",
    "-maxrate", "6800k",
    "-bufsize", "7000k",
    "-f", "flv", f"rtmp://a.rtmp.youtube.com/live2/{youtube_stream_key}"
]

def get_authenticated_service():
    credentials = None
    
    # Check if token.json exists and load credentials
    if os.path.exists(TOKEN_FILE):
        credentials = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    
    # If no valid credentials or credentials are expired, perform OAuth flow
    if not credentials or not credentials.valid:
        print("No valid credentials found. Starting OAuth flow...")
        flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
        credentials = flow.run_local_server(port=8080, prompt='consent')

        # Save credentials to file for future use
        with open(TOKEN_FILE, 'w') as token:
            token.write(credentials.to_json())

    # Build the YouTube API client
    youtube = build('youtube', 'v3', credentials=credentials)
    return youtube

def get_live_video_url(youtube):
    try:
        request = youtube.liveBroadcasts().list(
            part="snippet",
            broadcastType="all",
            broadcastStatus="active",
            maxResults=5
        )
        response = request.execute()
        print(response)
        
        if 'items' in response and len(response['items']) > 0:
            for item in response['items']:
                snippet = item['snippet']
                if 'actualStartTime' in snippet:
                    video_id = item['id']
                    youtube_watch_url = f"https://www.youtube.com/watch?v={video_id}"
                    youtube_embed_url = f"https://www.youtube.com/embed/{video_id}"
                    return youtube_embed_url, youtube_watch_url
        return None, None

    except HttpError as e:
        print(f"An HTTP error occurred: {e}")
        return None, None

def start_stream():
    global ffmpeg_process
    ffmpeg_process = subprocess.Popen(ffmpeg_command)

def insert_user_workout(username, startDT, workout, reps, percentage):
    # Define the Supabase insert payload
    payload = {
        "username": username,
        "startDT": startDT,
        "endDT": time.strftime("%Y-%m-%dT%H:%M:%SZ"),  # Get the current datetime
        "workout": workout,
        "reps": reps,
        "overallAccuracy": percentage
    }

    # Make the HTTP POST request to insert the record into Supabase
    headers = {
        "Content-Type": "application/json",
        "apikey": SUPABASE_API_KEY,
        "Authorization": f"Bearer {SUPABASE_API_KEY}"
    }
    
    url = f"{SUPABASE_URL}/rest/v1/{SUPABASE_WORKOUT_TABLE}"
    
    response = requests.post(url, json=payload, headers=headers)
    
    if response.status_code == 201:
        print(f"Record inserted into {SUPABASE_WORKOUT_TABLE}: {payload}")
    else:
        print(f"Failed to insert record: {response.text}")

def get_ngrok_url():
    try:
        response = requests.get("http://localhost:4040/api/tunnels")
        data = response.json()
        public_url = data['tunnels'][0]['public_url']
        return public_url
    except Exception as e:
        print(f"Error getting ngrok URL: {e}")
        return None




@app.route('/start', methods=['POST'])
def start():
    # Get data from the POST request
    data = request.get_json()
    workout = data.get("workout") # either pushups, squats or bicep curls

    global ffmpeg_process
    if ffmpeg_process is None:
        # Start the push_up.py script in a new thread/process
        ffmpeg_process = subprocess.Popen(['python', f'{workout}.py'])

        # Wait for the stream to initialize on YouTube
        time.sleep(20)  

        # Get the authenticated YouTube service
        youtube = get_authenticated_service()
        print(youtube)

        # Fetch the live video URLs after the stream has started
        youtube_embed_url, youtube_watch_url = get_live_video_url(youtube)

        if youtube_embed_url and youtube_watch_url:
            # Output a message through the speaker
            speak_text("The video stream has started successfully.")

            return jsonify({
                "message": "Stream started",
                "embed_url": youtube_embed_url,
                "watch_url": youtube_watch_url
            }), 200
        else:
            return jsonify({"message": "Stream started, but no live video found yet"}), 200
    else:
        return jsonify({"message": "Stream is already running"}), 400

@app.route('/stop', methods=['POST'])
def stop():
    global ffmpeg_process
    
    # Get data from the POST request
    data = request.get_json()
    username = data.get("username")
    startDT = data.get("startDT")
    workout = data.get("workout")
    
    if ffmpeg_process is not None:
        # Stop the ffmpeg process gracefully
        ffmpeg_process.send_signal(signal.SIGTERM)

        # Wait for the process to fully terminate
        ffmpeg_process.wait()  # This will block until the process terminates
        ffmpeg_process = None  # Reset the global variable

        # Wait till results.txt is written
        time.sleep(5)  

        # Read the count and success_rate from the result.txt file
        count = 0
        success_rate = 0.0
        try:
            with open('results.txt', 'r') as f:
                lines = f.readlines()
                for line in lines:
                    if "Count:" in line:
                        count = int(line.split(":")[1].strip())
                    elif "Success Rate:" in line:
                        success_rate = float(line.split(":")[1].strip().replace('%', ''))
        except FileNotFoundError:
            return jsonify({"message": "Result file not found"}), 400
        
        # Insert the workout data into Supabase
        insert_user_workout(username, startDT, workout, count, success_rate)
        
        return jsonify({"message": "Stream stopped and workout logged", "count": count, "success_rate": success_rate}), 200
    else:
        return jsonify({"message": "No stream is running"}), 400

def run_ngrok():
    # Set up an ngrok tunnel to the Flask app
    public_url = ngrok.connect(5000)  # Exposes port 5000
    print(f" * ngrok tunnel available at {public_url}")

@app.route('/ngrok-url', methods=['GET'])
def get_url():
    url = get_ngrok_url()
    if url:
        return jsonify({"ngrok_url": url}), 200
    else:
        return jsonify({"message": "Unable to get ngrok URL"}), 500


# Swagger setup
SWAGGER_URL = '/swagger'
API_URL = '/swagger.json'

swagger_spec = {
    "swagger": "2.0",
    "info": {
        "title": "YouTube Stream API",
        "description": "API for managing YouTube live streams and Supabase workout logs.",
        "version": "1.0.0"
    },
    "host": "localhost:5000",
    "schemes": ["http"],
    "paths": {
        "/start": {
            "post": {
                "summary": "Start YouTube stream",
                "description": "Starts a live YouTube stream and returns the stream URLs.",
                "parameters": [],
                "responses": {
                    "200": {
                        "description": "Stream started successfully"
                    },
                    "400": {
                        "description": "Stream is already running"
                    }
                }
            }
        },
        "/stop": {
            "post": {
                "summary": "Stop YouTube stream",
                "description": "Stops the live YouTube stream and logs the workout in Supabase.",
                "parameters": [
                    {
                        "name": "username",
                        "in": "body",
                        "description": "Username",
                        "required": True,
                        "schema": {"type": "string"}
                    },
                    {
                        "name": "startDT",
                        "in": "body",
                        "description": "Start date and time of the workout",
                        "required": True,
                        "schema": {"type": "string"}
                    },
                    {
                        "name": "workout",
                        "in": "body",
                        "description": "Workout type",
                        "required": True,
                        "schema": {"type": "string"}
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Stream stopped successfully and workout logged"
                    },
                    "400": {
                        "description": "No stream is running"
                    }
                }
            }
        },
        "/ngrok-url": {
            "get": {
                "summary": "Get ngrok URL",
                "description": "Returns the ngrok public URL.",
                "responses": {
                    "200": {
                        "description": "Ngrok URL fetched successfully"
                    },
                    "500": {
                        "description": "Unable to get ngrok URL"
                    }
                }
            }
        }
    }
}

# Set up Swagger UI blueprint
swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,  # URL for exposing Swagger UI
    API_URL,  # API spec path
    config={'app_name': "YouTube Stream API"}
)

# Register Swagger blueprint
app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)

@app.route('/swagger.json')
def swagger_json():
    return jsonify(swagger_spec)


if __name__ == '__main__':
    # Start ngrok in a separate thread
    ngrok_thread = threading.Thread(target=run_ngrok)
    ngrok_thread.start()

    # Start the Flask app
    app.run(host='0.0.0.0', port=5000)
