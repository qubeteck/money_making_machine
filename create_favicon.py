import struct

# Create a 16x16 favicon.ico with a blue background
# Header (6 bytes): reserved(2) + type(2) + count(2)
header = struct.pack('<HHH', 0, 1, 1)

# Directory entry (16 bytes): width(1) + height(1) + color rep(2) + planes(2) + bytes_in_res(4) + image_offset(2)
# For 16x16 32-bit icon: width=16, height=16, color rep=0, planes=1, bytes_in_res=0, image_offset=40
dir_entry = struct.pack('<BBBHHIH', 16, 0, 0, 1, 0, 40, 0)

# Image data: 16x16 pixels, 32-bit RGBA = 1024 bytes
# Blue color in RGBA order (B,G,R,A for Windows ICO): (0, 0, 255, 255)
# But actually for the image data in Windows ICO 32-bit, the bytes are stored as B,G,R,A
# Solid blue: B=0, G=0, R=255, A=255
blue_pixel = struct.pack('<BBBB', 0, 0, 255, 255)

# 1024 bytes of blue pixels (16*16*4)
blue_data = blue_pixel * 256

# Write the .ico file
with open('D:/Development/money_making_machine/app/static/favicon.ico', 'wb') as f:
    f.write(header)
    f.write(dir_entry)
    f.write(blue_data)

print('favicon.ico created successfully')