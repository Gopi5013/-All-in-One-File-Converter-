import cv2

img=cv2.imread("sk2.png")
gray=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)

inverted=255 - gray
blurred=cv2.GaussianBlur(inverted,(21,21),0)

sketch=cv2.divide(gray,255-blurred,\
                 scale=256)

cv2.imwrite("sketch4.jpg",sketch)
