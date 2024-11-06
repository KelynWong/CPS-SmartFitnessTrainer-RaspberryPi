# CPS-SmartFitnessTrainer-RaspberryPi
*note: make sure you have python version 3.11.X or below installed as mediapipe does not support higher versions*

## Instructions for windows
(Optional: Set up virtual environment - `python -m venv venv`)
(Optional: Activate virtual environment - `venv\Scripts\activate.bat`)
1. pip install -r requirements.txt
2. set up google oauth and enable youtube apis (https://console.cloud.google.com)
3. make sure ffmpeg is installed onto machine (https://ffmpeg.org/download.html)
4. make sure ngrok is installed onto machine (https://ngrok.com/download)
5. make sure espeak-ng is installed onto machine (https://github.com/espeak-ng/espeak-ng/releases)
6. run command: `cd integrate`
7. run command: `python windowsWebCamServer.py`


## Instructions for raspberry pi
(Optional: Set up virtual environment - `python -m venv venv`)
(Optional: Activate virtual environment - `source venv/bin/activate`)
1. pip install -r requirements.txt
2. set up google oauth and enable youtube apis (https://console.cloud.google.com)
3. make sure ffmpeg is installed onto machine (https://ffmpeg.org/download.html)
4. make sure ngrok is installed onto machine (https://ngrok.com/download)
5. make sure espeak-ng is installed onto machine (https://github.com/espeak-ng/espeak-ng/releases)
6. run command: `cd integrateRaspberry`
7. run command: `python raspberryWebCamServer.py`
