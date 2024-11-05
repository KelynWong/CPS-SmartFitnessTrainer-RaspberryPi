import os
import random
from flask import Flask, jsonify, request
import subprocess
import threading
import signal
import time
import requests
import pyttsx3
from flask_swagger_ui import get_swaggerui_blueprint
from supabase import create_client

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
heart_rate_data = []
heart_rate_thread = None
workout_active = False

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

def generate_heart_rate_data():
    """Generate random heart rate data every 10 seconds."""
    global heart_rate_data, workout_active

    while workout_active:
        # Generate a random heartbeat between 70 and 120 bpm
        heart_rate = random.randint(70, 120)
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ")  # Current timestamp
        heart_rate_data.append({"timestamp": timestamp, "heartrate": heart_rate})
        time.sleep(10)  # Wait for 10 seconds before generating the next reading

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

supabase = create_client(SUPABASE_URL, SUPABASE_API_KEY)

# # FFmpeg command
# ffmpeg_command = [
#     'C:\\Program Files\\ffmpeg-7.0.2-essentials_build\\bin\\ffmpeg',  # change path of ffmpeg here if needed
#     '-re',  # Read input file at native frame rate
#     '-i', 'output_pushup.mp4',  # The output file from push_up.py
#     "-s", "1920x1080",
#     "-r", "30",
#     "-vcodec", "libx264",
#     "-preset", "veryfast",
#     "-g", "60",  # Set keyframe interval (for 30 fps, 2 seconds interval = 60 frames)
#     "-acodec", "aac",
#     "-ar", "44100",
#     "-b:a", "128k",
#     "-b:v", "6800k",
#     "-maxrate", "6800k",
#     "-bufsize", "7000k",
#     "-f", "flv", f"rtmp://a.rtmp.youtube.com/live2/{youtube_stream_key}"
# ]

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

# def start_stream():
#     global ffmpeg_process
#     ffmpeg_process = subprocess.Popen(ffmpeg_command)

def insert_user_workout(username, startDT, workout, reps, percentage):
    payload = {
        "username": username,
        "startDT": startDT,
        "endDT": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "workout": workout,
        "reps": reps,
        "overallAccuracy": percentage
    }

    # Insert into Supabase using the client
    response = supabase.table(SUPABASE_WORKOUT_TABLE).insert(payload).execute()
    
    # Check for successful data insertion
    if response.data:
        print(f"Record inserted into {SUPABASE_WORKOUT_TABLE}: {response.data}")
        return response.data[0]
    else:
        print(f"Failed to insert record: {response}")
        return {"error": response}

def insert_heart_rate_data(workout_id, heart_rate_data):
    """Insert heart rate data into the userWorkoutHealth table using Supabase client."""
    errors = []
    print(heart_rate_data)
    
    for entry in heart_rate_data:
        payload = {
            "workout_id": workout_id,
            "timestamp": entry["timestamp"],
            "heartrate": entry["heartrate"]
        }

        # Insert the heart rate data into the userWorkoutHealth table
        response = supabase.table("userWorkoutHealth").insert(payload).execute()
        
        if not response.data:  # Check if data was not inserted successfully
            error_message = response.error.message if response.error else "Unknown error"
            errors.append(f"Failed to insert entry {payload}: {error_message}")
            print(f"Failed to insert heart rate data: {error_message}")
        else:
            print(f"Successfully inserted heart rate entry: {payload}")

    # If there were any errors, log them
    if errors:
        print("Errors occurred while inserting heart rate data:", errors)


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
    global ffmpeg_process, heart_rate_data, heart_rate_thread, workout_active

    # Reset heart rate data and set workout as active
    heart_rate_data = []
    workout_active = True

    # Get data from the POST request
    data = request.get_json()
    workout = data.get("workout")  # Either pushups, squats, or bicep curls

    if ffmpeg_process is None:
        # Start the heart rate generation thread
        heart_rate_thread = threading.Thread(target=generate_heart_rate_data)
        heart_rate_thread.start()

        # Start the workout script
        if workout in ["pushups", "bicepcurls", "squats"]:
            ffmpeg_process = subprocess.Popen(['python', f'{workout}.py'], 
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        else:
            workout_active = False  # Stop generating heart rate if workout is invalid
            return jsonify({"message": "Not a valid workout"}), 400

        # Wait for the stream to initialize on YouTube
        time.sleep(30)  

        youtube = get_authenticated_service()
        youtube_embed_url, youtube_watch_url = get_live_video_url(youtube)

        if youtube_embed_url and youtube_watch_url:
            speak_text("The video stream has started successfully.")
            return jsonify({"message": "Stream started", "embed_url": youtube_embed_url, "watch_url": youtube_watch_url}), 200
        else:
            return jsonify({"message": "Stream started, but no live video found yet"}), 200
    else:
        return jsonify({"message": "Stream is already running"}), 400


@app.route('/stop', methods=['POST'])
def stop():
    global ffmpeg_process, workout_active, heart_rate_data
    
    data = request.get_json()
    username = data.get("username")
    startDT = data.get("startDT")
    workout = data.get("workout")
    
    if ffmpeg_process is not None:
        workout_active = False  # Stop heart rate generation
        heart_rate_thread.join()  # Wait for the heart rate thread to finish

        ffmpeg_process.stdin.write(b'q\n')
        ffmpeg_process.stdin.flush()
        time.sleep(5)  
        ffmpeg_process.wait()
        ffmpeg_process = None

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
        
        # Insert the workout data into Supabase and get the workout_id
        workout_result = insert_user_workout(username, startDT, workout, count, success_rate)
        workout_id = workout_result.get("workout_id") if workout_result else None

        # Insert heart rate data into the userWorkoutHealth table
        if workout_id:
            insert_heart_rate_data(workout_id, heart_rate_data)
            return jsonify({"message": "Stream stopped, workout and heart rate logged", "payload": workout_result}), 200
        else:
            return jsonify({"message": "Insertion into database failed"}), 400
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
                "description": "Starts a live YouTube stream with the specified workout type and returns the stream URLs.",
                "parameters": [
                    {
                        "name": "workout",
                        "in": "body",
                        "description": "Type of workout to stream (e.g., pushups, squats, bicepcurls).",
                        "required": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "workout": {
                                    "type": "string",
                                    "enum": ["pushups", "squats", "bicepcurls"]  
                                }
                            }
                        }
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Stream started successfully",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "message": {
                                    "type": "string",
                                    "example": "Stream started"
                                },
                                "embed_url": {
                                    "type": "string",
                                    "example": "https://youtube.com/embed/live_stream?channel=CHANNEL_ID"
                                },
                                "watch_url": {
                                    "type": "string",
                                    "example": "https://youtube.com/watch?v=VIDEO_ID"
                                }
                            }
                        }
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
                        "name": "body",
                        "in": "body",
                        "description": "Workout logging details.",
                        "required": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "username": {
                                    "type": "string",
                                    "description": "Username of the person who performed the workout"
                                },
                                "startDT": {
                                    "type": "string",
                                    "description": "Start date and time of the workout (ISO format)"
                                },
                                "workout": {
                                    "type": "string",
                                    "description": "Type of workout (e.g., pushups, squats, bicep curls)"
                                }
                            },
                            "required": ["username", "startDT", "workout"]
                        }
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Stream stopped successfully and workout logged",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "message": {
                                    "type": "string",
                                    "example": "Stream stopped and workout logged"
                                },
                                "payload": {
                                    "type": "integer",
                                    "description": "Database insertion result"
                                }
                            }
                        }
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
