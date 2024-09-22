import os
from flask import Flask, jsonify
import subprocess
import threading
import signal
import time
import requests

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

# Load environment variables from .env file
load_dotenv()

youtube_stream_key = os.getenv("YOUTUBE_STREAM_KEY")
youtube_channel_id = os.getenv("YOUTUBE_CHANNEL_ID")

# OAuth 2.0 setup
CLIENT_SECRETS_FILE = os.getenv("CLIENT_SECRETS_FILE")
TOKEN_FILE = os.getenv("TOKEN_FILE")
SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]

# FFmpeg command
ffmpeg_command = [
    'C:\\Program Files\\ffmpeg-7.0.2-essentials_build\\bin\\ffmpeg', # change path of ffmpeg here if needed
    "-rtbufsize", "300M",
    "-f", "dshow",
    "-i", "video=Integrated Camera",
    "-f", "dshow",
    "-i", "audio=Microphone Array (Intel® Smart Sound Technology for Digital Microphones)",
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
    print(credentials.valid)
    # If no valid credentials or credentials are expired, perform OAuth flow
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())  # Refresh credentials if expired
        else:
            # Run the OAuth flow to get new credentials
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

@app.route('/start', methods=['POST'])
def start():
    global ffmpeg_process
    if ffmpeg_process is None:
        # Start the stream in a new thread
        thread = threading.Thread(target=start_stream)
        thread.start()

        # Wait for the stream to initialize on YouTube
        time.sleep(20)  # Adjust the wait time if necessary

        # Get the authenticated YouTube service
        youtube = get_authenticated_service()
        print(youtube)

        # Fetch the live video URLs after the stream has started
        youtube_embed_url, youtube_watch_url = get_live_video_url(youtube)

        if youtube_embed_url and youtube_watch_url:
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
    if ffmpeg_process is not None:
        ffmpeg_process.send_signal(signal.SIGTERM)  # Gracefully stop FFmpeg
        ffmpeg_process = None
        return jsonify({"message": "Stream stopped"}), 200
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

def get_ngrok_url():
    try:
        response = requests.get("http://localhost:4040/api/tunnels")
        data = response.json()
        public_url = data['tunnels'][0]['public_url']
        return public_url
    except Exception as e:
        print(f"Error getting ngrok URL: {e}")
        return None

if __name__ == '__main__':
    # Start ngrok in a separate thread
    ngrok_thread = threading.Thread(target=run_ngrok)
    ngrok_thread.start()

    # Start the Flask app
    app.run(host='0.0.0.0', port=5000)
