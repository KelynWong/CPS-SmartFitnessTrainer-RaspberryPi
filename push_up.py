import cv2
import mediapipe as mp
import numpy as np
import PoseModule as pm


cap = cv2.VideoCapture(0)
cap.set(3, 1280)  # Set width
cap.set(4, 720)   # Set height
detector = pm.poseDetector()
# attempts = 0 - this for counting total number of attempted pushups
count = 0
direction = 0
form = 0
feedback = "Fix Form"

# Create a full-screen window
cv2.namedWindow('Pushup counter', cv2.WND_PROP_FULLSCREEN)
cv2.setWindowProperty('Pushup counter', cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

while cap.isOpened():
    ret, img = cap.read() #640 x 480

    height, width, _ = img.shape # Get frame dimensions
    
    img = detector.findPose(img, False)
    lmList = detector.findPosition(img, False)

    if len(lmList) != 0:

        # Calculate angles for both arms
        right_elbow = detector.findAngle(img, 11, 13, 15)
        right_shoulder = detector.findAngle(img, 13, 11, 23)
        right_hip = detector.findAngle(img, 11, 23, 25)

        left_elbow = detector.findAngle(img, 12, 14, 16)
        left_shoulder = detector.findAngle(img, 14, 12, 24)
        left_hip = detector.findAngle(img, 12, 24, 26)

        # Percentage and bar for the progress bar, np.interp maps the values to a range
        per = np.interp(right_elbow, (90, 160), (0, 100))
        bar = np.interp(right_elbow, (90, 160), (380, 50))

        # Check to ensure right form before starting the program (Checks both arms)
        if right_elbow > 160 and right_shoulder > 40 and right_hip > 160 and \
           left_elbow > 160 and left_shoulder > 40 and left_hip > 160:
            form = 1
    
        # Check for full range of motion for the push-up
        if form == 1:
            if per == 0:                    # Check if the arms are fully extended, top position
                if right_elbow <= 90 and right_hip > 160 and \
                   left_elbow <= 90 and left_hip > 160:
                    feedback = "Up"
                    if direction == 0:
                        direction = 1
                else:
                    feedback = "Fix Form"

            if per == 100:                  # Check if the arms are fully bent, bottom position
                if right_elbow > 160 and right_shoulder > 40 and right_hip > 160 and \
                   left_elbow > 160 and left_shoulder > 40 and left_hip > 160:
                    feedback = "Down"
                    if direction == 1:
                        count += 1  # Only add 1 count when push-up is complete
                        direction = 0
                else:
                    feedback = "Fix Form"

        print(count)

        # Draw the pushup count in the bottom left corner
        cv2.rectangle(img, (0, height - 100), (150, height), (0, 255, 0), cv2.FILLED)
        cv2.putText(img, str(count), (25, height - 25), cv2.FONT_HERSHEY_PLAIN, 5, (255, 0, 0), 5)

        # Draw the feedback text in the top right corner
        cv2.rectangle(img, (width - 200, 0), (width, 40), (255, 255, 255), cv2.FILLED)
        cv2.putText(img, feedback, (width - 200 + 10, 30), cv2.FONT_HERSHEY_PLAIN, 2, (0, 255, 0), 2)

        # Progress bar
        if form == 1:  # Ensure progress bar is drawn only when the form is valid
            cv2.rectangle(img, (width - 30, 50), (width - 10, 380), (0, 255, 0), 3)  # Outline of the bar
            cv2.rectangle(img, (width - 30, int(bar)), (width - 10, 380), (0, 255, 0), cv2.FILLED)  # Filled bar
            cv2.putText(img, f'{int(per)}%', (width - 90, 430), cv2.FONT_HERSHEY_PLAIN, 2, (255, 0, 0), 2) # Percentage

    cv2.imshow('Pushup counter', img)
    if cv2.waitKey(10) & 0xFF == ord('q'):
        break
        
cap.release()
cv2.destroyAllWindows()
