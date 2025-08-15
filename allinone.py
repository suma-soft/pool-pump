#!/usr/bin/python
# -*- coding:utf-8 -*-

import sys
import os
import logging
import time
import traceback
import threading
import tkinter as tk
from tkinter import StringVar
import queue
import RPi.GPIO as GPIO
from PIL import Image, ImageTk, ImageDraw, ImageFont

# Paths to directories
picdir = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'pic')
libdir = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'lib')
if os.path.exists(libdir):
    sys.path.append(libdir)

from waveshare_OLED import OLED_0in96
from w1thermsensor import W1ThermSensor

logging.basicConfig(level=logging.DEBUG)

# Initialize GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
light_sensor = 2
relay = 17
GPIO.setup(light_sensor, GPIO.IN)
GPIO.setup(relay, GPIO.OUT)

# Initialize temperature sensors
DS1 = W1ThermSensor(sensor_id='085dd4465446')
DS2 = W1ThermSensor(sensor_id='5f43d4461686')
DS3 = W1ThermSensor(sensor_id='68e3d4465a14')

# Display available temperature sensors
for sensor in W1ThermSensor.get_available_sensors():
    print("Sensor %s has temperature %.2f" % (sensor.id, sensor.get_temperature()))

# Initialize OLED display
disp = OLED_0in96.OLED_0in96()
logging.info("0.96inch OLED")
disp.Init()
disp.clear()

# Initial state based on light sensor
initial_light_state = GPIO.input(light_sensor)
light_status = initial_light_state == 0
GPIO.output(relay, not light_status)

# GUI setup
root = tk.Tk()
root.title("Temperature and Pump Status")

# Create a frame to hold the labels at the top
top_frame = tk.Frame(root)
top_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

temp1_var = StringVar()
temp2_var = StringVar()
temp3_var = StringVar()
pump_status_var = StringVar()

# Kolejno?? etykiet (Wej\u015Bcie nad Wyj\u015Bciem)
temp2_label = tk.Label(top_frame, textvariable=temp2_var, font=('Helvetica', 16), anchor='center')
temp2_label.pack(anchor='center')
temp1_label = tk.Label(top_frame, textvariable=temp1_var, font=('Helvetica', 16), anchor='center')
temp1_label.pack(anchor='center')
temp3_label = tk.Label(top_frame, textvariable=temp3_var, font=('Helvetica', 16), anchor='center')
temp3_label.pack(anchor='center')
pump_status_label = tk.Label(top_frame, textvariable=pump_status_var, font=('Helvetica', 16), anchor='center')
pump_status_label.pack(anchor='center')

# Load BMP images
pump_on_image = Image.open(os.path.join(picdir, 'on.bmp'))
pump_on_photo = ImageTk.PhotoImage(pump_on_image)
pump_off_image = Image.open(os.path.join(picdir, 'off.bmp'))
pump_off_photo = ImageTk.PhotoImage(pump_off_image)

# Add pump image label at the top
pump_image_label = tk.Label(top_frame, image=(pump_on_photo if light_status else pump_off_photo))
pump_image_label.pack(anchor='center')

# Create a queue for thread-safe GUI updates
gui_queue = queue.Queue()

def update_gui():
    while True:
        try:
            data = gui_queue.get_nowait()
        except queue.Empty:
            break
        else:
            if data[0] == 'temp1':
                temp1_var.set(data[1])
            elif data[0] == 'temp2':
                temp2_var.set(data[1])
            elif data[0] == 'temp3':
                temp3_var.set(data[1])
            elif data[0] == 'pump':
                pump_status_var.set(data[1])
                if data[1].endswith('ON'):
                    pump_image_label.config(image=pump_on_photo)
                else:
                    pump_image_label.config(image=pump_off_photo)
    root.after(100, update_gui)

def get_light_status():
    global light_status
    light = GPIO.input(light_sensor)
    if light == 0:
        if not light_status:
            GPIO.output(relay, False)
            light_status = True
    else:
        if light_status:
            GPIO.output(relay, True)
            light_status = False
    return light_status

def sensor_thread():
    while True:
        temp1 = DS1.get_temperature()
        temp2 = DS2.get_temperature()
        temp3 = DS3.get_temperature()

        # polskie litery zapisane jako \u... ; stopnie jako \N{DEGREE SIGN}
        pump_status = 'w\u0142\u0105czona' if get_light_status() else 'wy\u0142\u0105czona'
        gui_queue.put(('temp2', f'Wej\u015Bcie: {temp2:.2f} \N{DEGREE SIGN}C'))
        gui_queue.put(('temp1', f'Wyj\u015Bcie: {temp1:.2f} \N{DEGREE SIGN}C'))
        gui_queue.put(('temp3', f'Powietrze: {temp3:.2f} \N{DEGREE SIGN}C'))
        gui_queue.put(('pump', f'Pompa: {pump_status}'))

        image1 = Image.new('1', (disp.width, disp.height), "WHITE")
        draw = ImageDraw.Draw(image1)
        font1 = ImageFont.truetype(os.path.join(picdir, 'Font.ttc'), 10)

        draw.line([(0, 15), (127, 15)], fill=0)
        draw.line([(0, 35), (127, 35)], fill=0)
        draw.line([(40, 0), (40, 35)], fill=0)
        draw.line([(84, 0), (84, 35)], fill=0)

        # zamienione miejsca: Wej\u015Bcie \u2192 segment \u015Brodkowy (46,0), Wyj\u015Bcie \u2192 lewy (0,0)
        draw.text((46, 0), 'Wej\u015Bcie', font=font1, fill=0)
        draw.text((46, 20), f'{temp2:.2f} \N{DEGREE SIGN}C', font=font1, fill=0)

        draw.text((0, 0), 'Wyj\u015Bcie', font=font1, fill=0)
        draw.text((0, 20), f'{temp1:.2f} \N{DEGREE SIGN}C', font=font1, fill=0)

        draw.text((92, 0), 'Powietrze', font=font1, fill=0)
        draw.text((92, 20), f'{temp3:.2f} \N{DEGREE SIGN}C', font=font1, fill=0)

        if light_status:
            draw.text((0, 45), 'Pump ON', font=font1, fill=0)
            bmp = Image.open(os.path.join(picdir, 'on.bmp'))
        else:
            draw.text((0, 45), 'Pump OFF', font=font1, fill=0)
            bmp = Image.open(os.path.join(picdir, 'off.bmp'))

        image1.paste(bmp, (50, 40))

        if temp2 >= 28.0:
            sun_bmp = Image.open(os.path.join(picdir, 'sun.bmp'))
            image1.paste(sun_bmp, (90, 40))

        disp.ShowImage(disp.getbuffer(image1))
        time.sleep(5)

sensor_thread = threading.Thread(target=sensor_thread)
sensor_thread.daemon = True
sensor_thread.start()

update_gui()
root.mainloop()

try:
    while True:
        get_light_status()
        time.sleep(1)
except IOError as e:
    logging.info(e)
except KeyboardInterrupt:
    logging.info("ctrl + c:")
    disp.module_exit()
    GPIO.cleanup()
    exit()
