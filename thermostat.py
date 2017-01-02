### BEGIN LICENSE
# Copyright (c) 2016 Jpnos <jpnos@gmx.com>

# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation
# files (the "Software"), to deal in the Software without
# restriction, including without limitation the rights to use,
# copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following
# conditions:

# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
# OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
# WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.
### END LICENSE

##############################################################################
#                                                                            #
#       Core Imports                                                         #
#                                                                            #
##############################################################################
import threading
import math
import os, os.path, sys
import time
import datetime
import urllib2
import json
import random
import socket
import re
import subprocess32
import locale
locale.setlocale(locale.LC_ALL, '')

##############################################################################
#                                                                            #
#       Kivy UI Imports                                                      #
#                                                                            #
##############################################################################

import kivy
kivy.require( '1.9.0' ) # replace with your current kivy version !

from kivy.app import App
from kivy.uix.button import Button
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.label import Label
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.image import Image
from kivy.uix.slider import Slider
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from kivy.storage.jsonstore import JsonStore
from kivy.uix.screenmanager import ScreenManager, Screen, NoTransition


##############################################################################
#                                                                            #
#       Other Imports                                                        #
#                                                                            #
##############################################################################

import cherrypy
import schedule
import struct
from bluepy.btle import *

##############################################################################
#                                                                            #
#       GPIO & Simulation Imports                                            #
#                                                                            #
##############################################################################

try:
	import RPi.GPIO as GPIO
except ImportError:
	import FakeRPi.GPIO as GPIO


##############################################################################
#                                                                            #
#       Sensor Imports                                                       #
#                                                                            #
##############################################################################

from w1thermsensor import W1ThermSensor


##############################################################################
#                                                                            #
#       Utility classes                                                      #
#                                                                            #
##############################################################################

class switch(object):
    def __init__(self, value):
        self.value = value
        self.fall = False

    def __iter__(self):
        """Return the match method once, then stop"""
        yield self.match
        raise StopIteration
    
    def match(self, *args):
        """Indicate whether or not to enter a case suite"""
        if self.fall or not args:
            return True
        elif self.value in args: # changed for v1.5, see below
            self.fall = True
            return True
        else:
            return False


##############################################################################
#                                                                            #
#       MySensor.org Controller compatible translated constants              #
#                                                                            #
##############################################################################

MSG_TYPE_SET 					= "set"
MSG_TYPE_PRESENTATION 				= "presentation"

CHILD_DEVICE_NODE				= "node"
CHILD_DEVICE_UICONTROL_HEAT			= "heatControl"
CHILD_DEVICE_UICONTROL_FAN			= "fanControl"
CHILD_DEVICE_UICONTROL_HOLD			= "holdControl"
CHILD_DEVICE_UICONTROL_SLIDER			= "tempSlider"
CHILD_DEVICE_WEATHER_FCAST_TODAY		= "weatherForecastToday"
CHILD_DEVICE_WEATHER_FCAST_TOMO			= "weatherForecastTomorrow"
CHILD_DEVICE_WEATHER_CURR			= "weatherCurrent"
CHILD_DEVICE_HEAT				= "heat"
CHILD_DEVICE_FAN				= "fan"
CHILD_DEVICE_PIR				= "motionSensor"
CHILD_DEVICE_TEMP				= "temperatureSensor"
CHILD_DEVICE_SCREEN				= "screen"
CHILD_DEVICE_SCHEDULER				= "scheduler"
CHILD_DEVICE_WEBSERVER				= "webserver"

CHILD_DEVICES						= [
	CHILD_DEVICE_NODE,
	CHILD_DEVICE_UICONTROL_HEAT,
	CHILD_DEVICE_UICONTROL_FAN,
	CHILD_DEVICE_UICONTROL_HOLD,
	CHILD_DEVICE_UICONTROL_SLIDER,
	CHILD_DEVICE_WEATHER_CURR,
	CHILD_DEVICE_WEATHER_FCAST_TODAY,
	CHILD_DEVICE_WEATHER_FCAST_TOMO,
	CHILD_DEVICE_HEAT,
	CHILD_DEVICE_FAN,
	CHILD_DEVICE_PIR,
	CHILD_DEVICE_TEMP,
	CHILD_DEVICE_SCREEN,
	CHILD_DEVICE_SCHEDULER,
	CHILD_DEVICE_WEBSERVER
]

CHILD_DEVICE_SUFFIX_UICONTROL		= "Control"

MSG_SUBTYPE_NAME			= "sketchName"
MSG_SUBTYPE_VERSION			= "sketchVersion"
MSG_SUBTYPE_BINARY_STATUS		= "binaryStatus"
MSG_SUBTYPE_TRIPPED			= "armed"
MSG_SUBTYPE_ARMED			= "tripped"
MSG_SUBTYPE_TEMPERATURE			= "temperature"
MSG_SUBTYPE_FORECAST			= "forecast"
MSG_SUBTYPE_CUSTOM			= "custom"
MSG_SUBTYPE_TEXT			= "text"


##############################################################################
#                                                                            #
#       Settings                                                             #
#                                                                            #
##############################################################################

THERMOSTAT_VERSION = "2.1.0"

# Debug settings

debug = False
useTestSchedule = False


# Threading Locks

thermostatLock = threading.RLock()
weatherLock    = threading.Lock()
scheduleLock   = threading.RLock()


# Thermostat persistent settings

settings	= JsonStore( "thermostat_settings.json" )
state		= JsonStore( "thermostat_state.json" )

#graphics


# Logging settings/setup

LOG_FILE_NAME = "./log/thermostat.log"

LOG_ALWAYS_TIMESTAMP = True

LOG_LEVEL_DEBUG = 1
LOG_LEVEL_INFO	= 2
LOG_LEVEL_ERROR = 3
LOG_LEVEL_STATE = 4
LOG_LEVEL_NONE  = 5

LOG_LEVELS = {
	"debug": LOG_LEVEL_DEBUG,
	"info":  LOG_LEVEL_INFO,
	"state": LOG_LEVEL_STATE,
	"error": LOG_LEVEL_ERROR
}

LOG_LEVELS_STR = { v: k for k, v in LOG_LEVELS.items() }

logFile = None


def log_dummy( level, child_device, msg_subtype, msg, msg_type=MSG_TYPE_SET, timestamp=True, single=False ):
	pass


def log_file( level, child_device, msg_subtype, msg, msg_type=MSG_TYPE_SET, timestamp=True, single=False ):
	if level >= logLevel:
		ts = datetime.datetime.now().strftime( "%Y-%m-%dT%H:%M:%S%z " ) 
		logFile.write( ts + LOG_LEVELS_STR[ level ] + "/" + child_device + "/" + msg_type + "/" + msg_subtype + ": " + msg + "\n" )


def log_print( level, child_device, msg_subtype, msg, msg_type=MSG_TYPE_SET, timestamp=True, single=False ):
	if level >= logLevel:
		ts = datetime.datetime.now().strftime( "%Y-%m-%dT%H:%M:%S%z " ) if LOG_ALWAYS_TIMESTAMP or timestamp else ""
		print( ts + LOG_LEVELS_STR[ level ] + "/" + child_device + "/" + msg_type + "/" + msg_subtype + ": " + msg )


loggingChannel = "none" if not( settings.exists( "logging" ) ) else settings.get( "logging" )[ "channel" ]
loggingLevel   = "state" if not( settings.exists( "logging" ) ) else settings.get( "logging" )[ "level" ]

for case in switch( loggingChannel ):
	if case( 'none' ):
		log = log_dummy
		break
	if case( 'file' ):
		log = log_file
		logFile = open( LOG_FILE_NAME, "a", 0 )
		break
	if case( 'print' ):
		log = log_print
		break
	if case():		# default
		log = log_dummy	

logLevel = LOG_LEVELS.get( loggingLevel, LOG_LEVEL_NONE )

# Send presentations for Node

log( LOG_LEVEL_STATE, CHILD_DEVICE_NODE, MSG_SUBTYPE_NAME, "Thermostat Starting Up...", msg_type=MSG_TYPE_PRESENTATION )
log( LOG_LEVEL_STATE, CHILD_DEVICE_NODE, MSG_SUBTYPE_VERSION, THERMOSTAT_VERSION, msg_type=MSG_TYPE_PRESENTATION )

#send presentations for all other child "sensors"

for i in range( len( CHILD_DEVICES ) ):
	child = CHILD_DEVICES[ i ]
	if child != CHILD_DEVICE_NODE:
		log( LOG_LEVEL_STATE, child, child, "", msg_type=MSG_TYPE_PRESENTATION )

# Various temperature settings:

tempScale		= settings.get( "scale" )[ "tempScale" ]
scaleUnits 	  	= "c" if tempScale == "metric" else "f"
precipUnits		= " mm" if tempScale == "metric" else '"'
precipFactor		= 1.0 if tempScale == "metric" else 0.0393701
precipRound		= 0 if tempScale == "metric" else 1
sensorUnits		= W1ThermSensor.DEGREES_C if tempScale == "metric" else W1ThermSensor.DEGREES_F
windFactor		= 3.6 if tempScale == "metric" else 1.0
windUnits		= " km/h" if tempScale == "metric" else " mph"

TEMP_TOLERANCE		= 0.1 if tempScale == "metric" else 0.18

currentTemp		= 20.0 if tempScale == "metric" else 72.0
priorCorrected		= -100.0
setTemp			= 22.0 if not( state.exists( "state" ) ) else state.get( "state" )[ "setTemp" ]
setice			= 15.0 if not(settings.exists ( "thermostat")) else settings.get("thermostat")["tempice"]
tempHysteresis		= 0.5  if not( settings.exists( "thermostat" ) ) else settings.get( "thermostat" )[ "tempHysteresis" ]
temp_ble_correct	= 0
tempCheckInterval	= 3    if not( settings.exists( "thermostat" ) ) else settings.get( "thermostat" )[ "tempCheckInterval" ]

minUIEnabled		= 0    if not( settings.exists( "thermostat" ) ) else settings.get( "thermostat" )[ "minUIEnabled" ]
minUITimeout		= 3    if not( settings.exists( "thermostat" ) ) else settings.get( "thermostat" )[ "minUITimeout" ]
lightOff		= 10   if not( settings.exists( "thermostat" ) ) else settings.get( "thermostat" )[ "lightOff" ]

minUITimer		= None
lightOffTimer		= None
bleTimer		= None

bleTimeout		= 60 if not( settings.exists("thermostat")) else settings.get( "ble")["timeout"]
bleTimeout_correct	= 10 if not( settings.exists("thermostat")) else settings.get( "ble")["timeout_correct"]
bleEnabled 		= 0 if not( settings.exists( "thermostat" ) ) else settings.get( "ble" )[ "enabled" ]
bleCorrectEnabled 	= 0 if not( settings.exists( "thermostat" ) ) else settings.get( "ble" )[ "correct_enabled" ]

log( LOG_LEVEL_INFO, CHILD_DEVICE_NODE, MSG_SUBTYPE_CUSTOM + "/settings/temperature/tempScale", str( tempScale ), timestamp=False )
log( LOG_LEVEL_INFO, CHILD_DEVICE_NODE, MSG_SUBTYPE_CUSTOM + "/settings/temperature/scaleUnits", str( scaleUnits ), timestamp=False )
log( LOG_LEVEL_INFO, CHILD_DEVICE_NODE, MSG_SUBTYPE_CUSTOM + "/settings/temperature/precipUnits", str( precipUnits ), timestamp=False )
log( LOG_LEVEL_INFO, CHILD_DEVICE_NODE, MSG_SUBTYPE_CUSTOM + "/settings/temperature/precipFactor", str( precipFactor ), timestamp=False )
log( LOG_LEVEL_INFO, CHILD_DEVICE_NODE, MSG_SUBTYPE_CUSTOM + "/settings/temperature/sensorUnits", str( sensorUnits ), timestamp=False )
log( LOG_LEVEL_INFO, CHILD_DEVICE_NODE, MSG_SUBTYPE_CUSTOM + "/settings/temperature/windFactor", str( windFactor ), timestamp=False )
log( LOG_LEVEL_INFO, CHILD_DEVICE_NODE, MSG_SUBTYPE_CUSTOM + "/settings/temperature/windUnits", str( windUnits ), timestamp=False )
log( LOG_LEVEL_INFO, CHILD_DEVICE_NODE, MSG_SUBTYPE_CUSTOM + "/settings/temperature/currentTemp", str( currentTemp ), timestamp=False )
log( LOG_LEVEL_INFO, CHILD_DEVICE_NODE, MSG_SUBTYPE_CUSTOM + "/settings/temperature/setTemp", str( setTemp ), timestamp=False )
log( LOG_LEVEL_INFO, CHILD_DEVICE_NODE, MSG_SUBTYPE_CUSTOM + "/settings/temperature/tempHysteresis", str( tempHysteresis ), timestamp=False )
log( LOG_LEVEL_INFO, CHILD_DEVICE_NODE, MSG_SUBTYPE_CUSTOM + "/settings/temperature/tempCheckInterval", str( tempCheckInterval ), timestamp=False )
log( LOG_LEVEL_INFO, CHILD_DEVICE_NODE, MSG_SUBTYPE_CUSTOM + "/settings/temperature/minUIEnabled", str( minUIEnabled ), timestamp=False )
log( LOG_LEVEL_INFO, CHILD_DEVICE_NODE, MSG_SUBTYPE_CUSTOM + "/settings/temperature/minUITimeout", str( minUITimeout ), timestamp=False )
log( LOG_LEVEL_INFO, CHILD_DEVICE_NODE, MSG_SUBTYPE_CUSTOM + "/settings/temperature/lightOff", str( lightOff ), timestamp=False )

# Temperature calibration settings:

elevation	  = 0 if not( settings.exists( "thermostat" ) ) else settings.get( "calibration" )[ "elevation" ]
boilingPoint	  = ( 100.0 - 0.003353 * elevation ) if tempScale == "metric" else ( 212.0 - 0.00184 * elevation )
freezingPoint	  = 0.01 if tempScale == "metric" else 32.018
referenceRange	  = boilingPoint - freezingPoint

boilingMeasured   = settings.get( "calibration" )[ "boilingMeasured" ]
freezingMeasured  = settings.get( "calibration" )[ "freezingMeasured" ]
measuredRange	  = boilingMeasured - freezingMeasured

log( LOG_LEVEL_INFO, CHILD_DEVICE_NODE, MSG_SUBTYPE_CUSTOM + "/settings/calibration/elevation", str( elevation ), timestamp=False )
log( LOG_LEVEL_INFO, CHILD_DEVICE_NODE, MSG_SUBTYPE_CUSTOM + "/settings/calibration/boilingPoint", str( boilingPoint ), timestamp=False )
log( LOG_LEVEL_INFO, CHILD_DEVICE_NODE, MSG_SUBTYPE_CUSTOM + "/settings/calibration/freezingPoint", str( freezingPoint ), timestamp=False )
log( LOG_LEVEL_DEBUG, CHILD_DEVICE_NODE, MSG_SUBTYPE_CUSTOM + "/settings/calibration/referenceRange", str( referenceRange ), timestamp=False )
log( LOG_LEVEL_INFO, CHILD_DEVICE_NODE, MSG_SUBTYPE_CUSTOM + "/settings/calibration/boilingMeasured", str( boilingMeasured ), timestamp=False )
log( LOG_LEVEL_INFO, CHILD_DEVICE_NODE, MSG_SUBTYPE_CUSTOM + "/settings/calibration/freezingMeasured", str( freezingMeasured ), timestamp=False )
log( LOG_LEVEL_DEBUG, CHILD_DEVICE_NODE, MSG_SUBTYPE_CUSTOM + "/settings/calibration/measuredRange", str( measuredRange ), timestamp=False )


# UI Slider settings:

minTemp			  = 15.0 if not( settings.exists( "thermostat" ) ) else settings.get( "thermostat" )[ "minTemp" ]
maxTemp			  = 30.0 if not( settings.exists( "thermostat" ) ) else settings.get( "thermostat" )[ "maxTemp" ]
tempStep		  = 0.5  if not( settings.exists( "thermostat" ) ) else settings.get( "thermostat" )[ "tempStep" ]

log( LOG_LEVEL_INFO, CHILD_DEVICE_NODE, MSG_SUBTYPE_CUSTOM + "/settings/UISlider/minTemp", str( minTemp ), timestamp=False )
log( LOG_LEVEL_INFO, CHILD_DEVICE_NODE, MSG_SUBTYPE_CUSTOM + "/settings/UISlider/maxTemp", str( maxTemp ), timestamp=False )
log( LOG_LEVEL_INFO, CHILD_DEVICE_NODE, MSG_SUBTYPE_CUSTOM + "/settings/UISlider/tempStep", str( tempStep ), timestamp=False )

try:
	tempSensor = W1ThermSensor()
except:
	tempSensor = None


# PIR (Motion Sensor) setup:

pirEnabled 		= 0 if not( settings.exists( "pir" ) ) else settings.get( "pir" )[ "pirEnabled" ]
pirPin  		= 5 if not( settings.exists( "pir" ) ) else settings.get( "pir" )[ "pirPin" ]

pirCheckInterval 	= 0.5 if not( settings.exists( "pir" ) ) else settings.get( "pir" )[ "pirCheckInterval" ]

pirIgnoreFromStr	= "00:00" if not( settings.exists( "pir" ) ) else settings.get( "pir" )[ "pirIgnoreFrom" ]
pirIgnoreToStr		= "00:00" if not( settings.exists( "pir" ) ) else settings.get( "pir" )[ "pirIgnoreTo" ]

pirIgnoreFrom		= datetime.time( int( pirIgnoreFromStr.split( ":" )[ 0 ] ), int( pirIgnoreFromStr.split( ":" )[ 1 ] ) )
pirIgnoreTo		= datetime.time( int( pirIgnoreToStr.split( ":" )[ 0 ] ), int( pirIgnoreToStr.split( ":" )[ 1 ] ) )

log( LOG_LEVEL_INFO, CHILD_DEVICE_PIR, MSG_SUBTYPE_ARMED, str( pirEnabled ), timestamp=False )
log( LOG_LEVEL_INFO, CHILD_DEVICE_NODE, MSG_SUBTYPE_CUSTOM + "/settings/pir/checkInterval", str( pirCheckInterval ), timestamp=False )
log( LOG_LEVEL_INFO, CHILD_DEVICE_NODE, MSG_SUBTYPE_CUSTOM + "/settings/pir/ignoreFrom", str( pirIgnoreFromStr ), timestamp=False )
log( LOG_LEVEL_INFO, CHILD_DEVICE_NODE, MSG_SUBTYPE_CUSTOM + "/settings/pir/ignoreTo", str( pirIgnoreToStr ), timestamp=False )

# GPIO Pin setup and utility routines:

heatPin 			= 23 if not( settings.exists( "thermostat" ) ) else settings.get( "thermostat" )[ "heatPin" ]
fanPin  			= 25 if not( settings.exists( "thermostat" ) ) else settings.get( "thermostat" )[ "fanPin" ]
lightPin			= 24 if not( settings.exists( "thermostat" ) ) else settings.get( "thermostat" )[ "lightPin" ]

GPIO.setmode( GPIO.BCM )
GPIO.setup( heatPin, GPIO.OUT )
GPIO.output( heatPin, GPIO.HIGH )
GPIO.setup( fanPin, GPIO.OUT )
GPIO.output( fanPin, GPIO.HIGH )
GPIO.setup( lightPin, GPIO.OUT )
GPIO.output( lightPin, GPIO.HIGH )

if pirEnabled:
	GPIO.setup( pirPin, GPIO.IN )

CHILD_DEVICE_HEAT					= "heat"
CHILD_DEVICE_FAN					= "fan"

log( LOG_LEVEL_INFO, CHILD_DEVICE_HEAT, MSG_SUBTYPE_BINARY_STATUS, str( heatPin ), timestamp=False )
log( LOG_LEVEL_INFO, CHILD_DEVICE_FAN, MSG_SUBTYPE_BINARY_STATUS, str( fanPin ), timestamp=False )
log( LOG_LEVEL_INFO, CHILD_DEVICE_PIR, MSG_SUBTYPE_TRIPPED, str( pirPin ), timestamp=False )


##############################################################################
#                                                                            #
#       UI Controls/Widgets                                                  #
#                                                                            #
##############################################################################

controlColours = {
					"normal": ( 1.0, 1.0, 1.0, 1.0 ),
					"Cool":   ( 0.0, 0.0, 1.0, 0.4 ),
					"AUTO":   ( 4.0, 0.0, 0.0, 1.0 ),
					"Fan":    ( 0.0, 1.0, 0.0, 0.4 ),
					"MAN":   ( 0.5, 1.0, 0.0, 0.4 ),					
				 }


def setControlState( control, state ):
	with thermostatLock:
		control.state = state
		if state == "normal":
			control.background_color = controlColours[ "normal" ]
		else:
			control.background_color = controlColours[ control.text.replace( "[b]", "" ).replace( "[/b]", "" ) ]
		
		controlLabel = control.text.replace( "[b]", "" ).replace( "[/b]", "" ).lower()
		log( LOG_LEVEL_STATE, controlLabel +  CHILD_DEVICE_SUFFIX_UICONTROL, MSG_SUBTYPE_BINARY_STATUS, "0" if state == "normal" else "1" )

heatControl = ToggleButton( text="[b]AUTO[/b]", 
				markup=True, 
				size_hint = ( None, None )
				)

setControlState( heatControl, "normal" if not( state.exists( "state" ) ) else state.get( "state" )[ "heatControl" ] )

fanControl  = ToggleButton( text="[b]Fan[/b]", 
				markup=True, 
				size_hint = ( None, None )
				)

setControlState( fanControl, "normal" if not( state.exists( "state" ) ) else state.get( "state" )[ "fanControl" ] )

holdControl = ToggleButton( text="[b]MAN[/b]", 
				markup=True, 
				size_hint = ( None, None )
				)

setControlState( holdControl, "normal" if not( state.exists( "state" ) ) else state.get( "state" )[ "holdControl" ] )



def get_status_string():
	with thermostatLock:
		temperature = 0
		if holdControl.state == "down":
			sched = "MAN"
			temperature = setTemp
		elif useTestSchedule:
			sched = "Test"
			temperature = setTemp
		elif heatControl.state == "down":
			sched = "AUTO"
			temperature = setTemp
		else:
		    sched = "No Ice" 
		    temperature = settings.get("thermostat")["tempice"]
		    testAUTO = False
		    
		if GPIO.input( heatPin ) == True:
			testAUTO = False
		else:
			testAUTO = True
	
		return "[b] [/b]\n  " + \
			   "Set:    " +str(temperature)+"c \n  "+\
			   "Caldaia:      " + ( "[b]On[/b]" if testAUTO else "Off" ) + "\n  "+\
			   "Modo:   " + sched


versionLabel	= Label( text="Thermostat v" + str( THERMOSTAT_VERSION ), size_hint = ( None, None ), font_size='10sp', markup=True, text_size=( 150, 20 ) )
currentLabel	= Label( text="[b]" + str( currentTemp ) + scaleUnits + "[/b]", size_hint = ( None, None ), font_size='100sp', markup=True, text_size=( 300, 200 ) )
altCurLabel	= Label( text=currentLabel.text, size_hint = ( None, None ), font_size='100sp', markup=True, text_size=( 300, 200 ), color=( 0.5, 0.5, 0.5, 0.2 ) )

setLabel     = Label( text="  \n[b]" + str( setTemp ) + scaleUnits + "[/b]", size_hint = ( None, None ), font_size='25sp', markup=True, text_size=( 100, 80 ) )
statusLabel  = Label( text=get_status_string(), size_hint = ( None, None ),  font_size='30sp', markup=True, text_size=( 240, 230 ) )

altStatusLabel = Label( text=get_status_string(), size_hint = ( None, None),font_size='30sp', markup=True, text_size=( 240, 230 ),color=(0.5,0.5,0.5,0.2))

dateLabel	= Label( text="[b]" + time.strftime("%d %b %a, %Y") + "[/b]", size_hint = ( None, None ), font_size='22sp', markup=True, text_size=( 270, 40 ) )

timeStr		= time.strftime("%H:%M").lower()
timeInit	= time.time()

timeLabel	 = Label( text="[b]" + ( timeStr if timeStr[0:1] != "0" else timeStr[1:] ) + "[/b]", size_hint = ( None, None ), font_size='40sp', markup=True, text_size=( 185, 85 ) )
altTimeLabel = Label( text=timeLabel.text, size_hint = ( None, None ), font_size='40sp', markup=True, text_size=( 180, 75 ), color=( 0.5, 0.5, 0.5, 0.2 ) )

tempSlider 	 = Slider( orientation='vertical', min=minTemp, max=maxTemp, step=tempStep, value=setTemp, size_hint = ( None, None ) )

screenMgr    = None

ble_in =  Label( text="Init", size_hint = ( None, None ),  font_size='16sp', markup=True, text_size=( 300, 150 ), valign="top", color=(0.5,0.5,0.5,0.2))
ble_out =  Label( text="Init", size_hint = ( None, None ),  font_size='16sp', markup=True, text_size=( 300, 150 ), valign="top", color=(0.5,0.5,0.5,0.2))

##############################################################################
#                                                                            #
#       Weather functions/constants/widgets                                  #
#                                                                            #
##############################################################################

weatherLocation 	 = settings.get( "weather" )[ "location" ]
weatherAppKey		 = settings.get( "weather" )[ "appkey" ]
weatherURLBase  	 = "http://api.openweathermap.org/data/2.5/"
weatherURLForecast 	 = weatherURLBase + "forecast/daily?units=" + tempScale + "&id=" + weatherLocation + "&APPID=" + weatherAppKey + "&lang=it"
weatherURLTimeout 	 = settings.get( "weather" )[ "URLtimeout" ]
weatherURLCurrent 	 = weatherURLBase + "weather?units=" + tempScale + "&id=" + weatherLocation + "&APPID=" + weatherAppKey + "&lang=it"

forecastRefreshInterval  = settings.get( "weather" )[ "forecastRefreshInterval" ] * 60  
weatherExceptionInterval = settings.get( "weather" )[ "weatherExceptionInterval" ] * 60  
weatherRefreshInterval   = settings.get( "weather" )[ "weatherRefreshInterval" ] * 60

weatherSummaryLabel  = Label( text="", size_hint = ( None, None ), font_size='20sp', markup=True, text_size=( 200, 20 ) )
weatherDetailsLabel  = Label( text="", size_hint = ( None, None ), font_size='25sp', markup=True, text_size=( 300, 150 ), valign="top" )
weatherImg           = Image( source="web/images/na.png", size_hint = ( None, None ) )
weatherminSummaryLabel  = Label( text="", size_hint = ( None, None ), font_size='20sp', markup=True, text_size=( 200, 20 ), color=(0.5,0.5,0.5,0.2) )
weatherminImg           = Image( source="web/images/na.png", size_hint = ( None, None ), color=(1,1,1,0.4) )

bluetoothImg           = Image( source="web/images/bluetooth.png", size_hint = ( None, None ),color=(1,1,1,0) )
bluetoothMinImg           = Image( source="web/images/bluetooth.png", size_hint = ( None, None ), color=(1,1,1,0) )

forecastTodaySummaryLabel = Label( text="", size_hint = ( None, None ), font_size='15sp',  markup=True, text_size=( 100, 15 ) )
forecastTodayDetailsLabel = Label( text="", size_hint = ( None, None ), font_size='20sp',  markup=True, text_size=( 200, 150 ), valign="top" )
forecastTodayImg   		  = Image( source="web/images/na.png", size_hint = ( None, None ) )
forecastTomoSummaryLabel  = Label( text="", size_hint = ( None, None ), font_size='15sp', markup=True, text_size=( 100, 15 ))
forecastTomoDetailsLabel  = Label( text="", size_hint = ( None, None ), font_size='20sp', markup=True, text_size=( 200, 150 ), valign="top" )
forecastTomoImg    		  = Image( source="web/images/na.png", size_hint = ( None, None ) )


def get_weather( url ):
	return json.loads( urllib2.urlopen( url, None, weatherURLTimeout ).read() )



def get_cardinal_direction( heading ):
	directions = [ "N", "NE", "E", "SE", "S", "SW", "W", "NW", "N" ]
	return directions[ int( round( ( ( heading % 360 ) / 45 ) ) ) ]
	
	
def display_current_weather( dt ):
	with weatherLock:
		global ble_out
		interval = weatherRefreshInterval
		try:
			weather = get_weather( weatherURLCurrent )
			weatherImg.source = "web/images/" + weather[ "weather" ][ 0 ][ "icon" ] + ".png" 
#			weatherSummaryLabel.text = "[b]" + weather[ "weather" ][ 0 ][ "description" ].title() + "[/b]"
			weatherminImg.source = "web/images/" + weather[ "weather" ][ 0 ][ "icon" ] + ".png" 
			weatherminSummaryLabel.text = "[b]" + weather[ "weather" ][ 0 ][ "description" ].title() + "[/b]"
			if bleEnabled and ble_in.text != "None":
					temp_vis=ble_out.text
			else:
				temp_vis=str( int( round( weather[ "main" ][ "temp" ], 0 ) ) )
				
			weatherDetailsLabel.text = "\n".join( (
				" " + temp_vis + scaleUnits,
#				"Umidita:   " + str( weather[ "main" ][ "humidity" ] ) + "%",
#				"Vento:       " + str( int( round( weather[ "wind" ][ "speed" ] * windFactor ) ) ) + windUnits + " " + get_cardinal_direction( weather[ "wind" ][ "deg" ] ),
#				"Nuvole:     " + str( weather[ "clouds" ][ "all" ] ) + "%",
			) )

			log( LOG_LEVEL_INFO, CHILD_DEVICE_WEATHER_CURR, MSG_SUBTYPE_TEXT, weather[ "weather" ][ 0 ][ "description" ].title() + "; " + re.sub( '\n', "; ", re.sub( ' +', ' ', weatherDetailsLabel.text ).strip() ) )

		except:
			interval = weatherExceptionInterval

			weatherImg.source = "web/images/na.png"
			weatherSummaryLabel.text = ""
			weatherDetailsLabel.text = ""

			log( LOG_LEVEL_ERROR, CHILD_DEVICE_WEATHER_CURR, MSG_SUBTYPE_TEXT, "Update FAILED!" )

		Clock.schedule_once( display_current_weather, interval )

def display_forecast_weather( dt ):
	with weatherLock:
		interval = forecastRefreshInterval
		try:
			forecast = get_weather( weatherURLForecast )
			today    = forecast[ "list" ][ 0 ]
			tomo     = forecast[ "list" ][ 1 ]
			forecastTodayImg.source = "web/images/" + today[ "weather" ][ 0 ][ "icon" ] + ".png" 
			
#			forecastTodaySummaryLabel.text = "[b]" + today[ "weather" ][ 0 ][ "description" ].title() + "[/b]"		
			
			todayText = "\n".join( (
				"Max " + str( int( round( today[ "temp" ][ "max" ], 0 ) ) ) + scaleUnits + " Min " + str( int( round( today[ "temp" ][ "min" ], 0 ) ) ) + scaleUnits,
#				"Umidita:         "+ str( today[ "humidity" ] ) + "%",
#				"Vento:            " + str( int( round( today[ "speed" ] * windFactor ) ) ) + windUnits + " " + get_cardinal_direction( today[ "deg" ] ),
#				"Nuvole:          " + str( today[ "clouds" ] ) + "%",
			) )
#			if "rain" in today or "snow" in today:
#				todayText += "\n"
#				if "rain" in today:
#					todayText += "Pioggia:         " + get_precip_amount( today[ "rain" ] ) + precipUnits   
#					if "snow" in today:
#						todayText += ", Neve: " + get_precip_amount( today[ "snow" ] ) + precipUnits
#				else:
#					todayText += "Neve:         " + get_precip_amount( today[ "snow" ] ) + precipUnits
			forecastTodayDetailsLabel.text = todayText;

			forecastTomoImg.source = "web/images/" + tomo[ "weather" ][ 0 ][ "icon" ] + ".png" 

#			forecastTomoSummaryLabel.text = "[b]" + tomo[ "weather" ][ 0 ][ "description" ].title() + "[/b]"		
	
			
			tomoText = "\n".join( (
				"Max " + str( int( round( tomo[ "temp" ][ "max" ], 0 ) ) ) + scaleUnits + " Min " + str( int( round( tomo[ "temp" ][ "min" ], 0 ) ) ) + scaleUnits,
#				"Umidita:        " + str( tomo[ "humidity" ] ) + "%",
#				"Vento:           " + str( int( round( tomo[ "speed" ] * windFactor ) ) ) + windUnits + " " + get_cardinal_direction( tomo[ "deg" ] ),
#				"Nuvole:         " + str( tomo[ "clouds" ] ) + "%",
			) )

#			if "rain" in tomo or "snow" in tomo:
#				tomoText += "\n"
#				if "rain" in tomo:
#					tomoText += "Pioggia:        " + get_precip_amount( tomo[ "rain" ] ) + precipUnits
#					if "snow" in tomo:
#						tomoText += ", Neve: " + get_precip_amount( tomo[ "snow" ] ) + precipUnits
#				else:
#					tomoText += "Neve:        " + get_precip_amount( tomo[ "snow" ] ) + precipUnits

			forecastTomoDetailsLabel.text = tomoText

			log( LOG_LEVEL_INFO, CHILD_DEVICE_WEATHER_FCAST_TODAY, MSG_SUBTYPE_TEXT, today[ "weather" ][ 0 ][ "description" ].title() + "; " + re.sub( '\n', "; ", re.sub( ' +', ' ', forecastTodayDetailsLabel.text ).strip() ) )
			log( LOG_LEVEL_INFO, CHILD_DEVICE_WEATHER_FCAST_TOMO, MSG_SUBTYPE_TEXT, tomo[ "weather" ][ 0 ][ "description" ].title() + "; " + re.sub( '\n', "; ", re.sub( ' +', ' ', forecastTomoDetailsLabel.text ).strip() ) )

		except:
			interval = weatherExceptionInterval

			forecastTodayImg.source = "web/images/na.png"
			forecastTodaySummaryLabel.text = ""
			forecastTodayDetailsLabel.text = ""
			forecastTomoImg.source = "web/images/na.png"
			forecastTomoSummaryLabel.text = ""
			forecastTomoDetailsLabel.text = ""

			log( LOG_LEVEL_ERROR, CHILD_DEVICE_WEATHER_FCAST_TODAY, MSG_SUBTYPE_TEXT, "Update FAILED!" )

		Clock.schedule_once( display_forecast_weather, interval )
		
		
def get_precip_amount( raw ):
	precip = round( raw * precipFactor, precipRound )

	if tempScale == "metric":
		return str( int ( precip ) )
	else:
		return str( precip )


##############################################################################
#                                                                            #
#       Utility Functions                                                    #
#                                                                            #
##############################################################################

def get_ip_address():
	s = socket.socket( socket.AF_INET, socket.SOCK_DGRAM )
	s.settimeout( 10 )   # 10 seconds
	try:
		s.connect( ( "8.8.8.8", 80 ) )    # Google DNS server
		ip = s.getsockname()[0] 
		log( LOG_LEVEL_INFO, CHILD_DEVICE_NODE, MSG_SUBTYPE_CUSTOM +"/settings/ip", ip, timestamp=False )
	except socket.error:
		ip = "127.0.0.1"
		log( LOG_LEVEL_ERROR, CHILD_DEVICE_NODE, MSG_SUBTYPE_CUSTOM + "/settings/ip", "FAILED to get ip address, returning " + ip, timestamp=False )

	return ip


def getVersion():
	log( LOG_LEVEL_STATE, CHILD_DEVICE_NODE, MSG_SUBTYPE_VERSION, THERMOSTAT_VERSION )


def restart():
	log( LOG_LEVEL_STATE, CHILD_DEVICE_NODE, MSG_SUBTYPE_CUSTOM + "/restart", "Thermostat restarting...", single=True ) 
	GPIO.cleanup()

	if logFile is not None:
		logFile.flush()
		os.fsync( logFile.fileno() )
		logFile.close()

	os.execl( sys.executable, 'python', __file__, *sys.argv[1:] )	# This does not return!!!


def setLogLevel( msg ):
	global logLevel

	if LOG_LEVELS.get( msg.payload ):
		log( LOG_LEVEL_STATE, CHILD_DEVICE_NODE, MSG_SUBTYPE_CUSTOM + "/loglevel", "LogLevel set to: " + msg.payload ) 

		logLevel = LOG_LEVELS.get( msg.payload, logLevel )
	else:
		log( LOG_LEVEL_ERROR, CHILD_DEVICE_NODE, MSG_SUBTYPE_CUSTOM + "/loglevel", "Invalid LogLevel: " + msg.payload ) 

def restart_program():
    """Restarts the current program.
    Note: this function does not return. Any cleanup action (like
    saving data) must be done before calling this function."""
    python = sys.executable
    os.execl(python, python, * sys.argv)
    
##############################################################################
#                                                                            #
#       Thermostat Implementation                                            #
#                                                                            #
##############################################################################

# Main furnace/AC system control function:

def change_system_settings():
	with thermostatLock:
		hpin_start = str( GPIO.input( heatPin ) )
		fpin_start = str( GPIO.input( fanPin ) )
		global timeInit

		if heatControl.state == "down":
	
			if setTemp >= currentTemp + tempHysteresis:
				GPIO.output( heatPin, GPIO.LOW )
				GPIO.output( fanPin, GPIO.LOW )	
			elif setTemp <= currentTemp:
				GPIO.output( heatPin, GPIO.HIGH )
					
		else:
#modifica per minima temp antigelo 
			    if currentTemp <= setice and holdControl != "down":
				GPIO.output(heatPin,GPIO.LOW)
			    else:
				GPIO.output(heatPin,GPIO.HIGH)
				
			    if holdControl.state == "down":
			    	if setTemp >= currentTemp + tempHysteresis:
			    	    GPIO.output(heatPin, GPIO.LOW)
			    	else:
				    GPIO.output( heatPin, GPIO.HIGH )


		# save the thermostat state in case of restart
		state.put( "state", setTemp=setTemp, heatControl=heatControl.state, fanControl=fanControl.state, holdControl=holdControl.state)
		# save graph
		#print timeInit,time.time() schedule on 10 minuti
		postTime=timeInit + 300 
		
		 
		#print postTime
		if postTime <= time.time():
			tempSet=setice
			if heatControl.state == "down":
				tempSet = setTemp
			else:
				if holdControl.state == "down":
					tempSet = setTemp
		
		#conversione heatpin in temperatura 10=off 12=on
			switchTemp = 10
			if GPIO.input( heatPin ) == True:
				switchTemp = 10
			else:
				switchTemp = 12	
			#scrivo il file csv con i dati 
			if os.path.isfile("./web/graph/" + "thermostat.csv"):
				out_file=open (("./web/graph/" + "thermostat.csv"),"a")
				out_file.write (time.strftime("%Y/%m/%d %H:%M:%S", time.localtime())+", "+str(tempSet)+", "+str(currentTemp)+ ", " + str(switchTemp)+ "\n")
				out_file.close()
				timeInit=time.time()
			else:
				out_file=open (("./web/graph/" + "thermostat.csv"),"a")
				out_file.write("Time, setTemp,  TempRilevata, Switch \n")
				out_file.write (time.strftime("%Y/%m/%d %H:%M:%S", time.localtime())+", "+str(tempSet)+", "+str(currentTemp)+ ", " + str(switchTemp)+"\n")
				out_file.close()
				timeInit=time.time()
			
		
		statusLabel.text = get_status_string()
		altStatusLabel.text = get_status_string()

		if hpin_start != str( GPIO.input( heatPin ) ):
			log( LOG_LEVEL_STATE, CHILD_DEVICE_HEAT, MSG_SUBTYPE_BINARY_STATUS, "1" if GPIO.input( heatPin ) else "0" )
		if fpin_start != str( GPIO.input( fanPin ) ):
			log( LOG_LEVEL_STATE, CHILD_DEVICE_FAN, MSG_SUBTYPE_BINARY_STATUS, "1" if GPIO.input( fanPin ) else "0" )


# This callback will be bound to the touch screen UI buttons:

def control_callback( control ):
	with thermostatLock:
		setControlState( control, control.state ) 	# make sure we change the background colour!

		if control is heatControl:
			if control.state == "down":
				setControlState( holdControl, "normal" )
			reloadSchedule()
		if control is holdControl:
			if control.state == "down":
				setControlState(heatControl, "normal" )
			reloadSchedule()						

# Check the current sensor temperature

def check_sensor_temp( dt ):
	with thermostatLock:
		global currentTemp, priorCorrected
		global tempSensor
		global temp_ble_correct
		global ble_correct_enabled
		if tempSensor is not None:
			rawTemp = tempSensor.get_temperature( sensorUnits )
			correctedTemp = ( ( ( rawTemp - freezingMeasured ) * referenceRange ) / measuredRange ) + freezingPoint
			currentTemp = round( correctedTemp, 1 )
			log( LOG_LEVEL_DEBUG, CHILD_DEVICE_TEMP, MSG_SUBTYPE_CUSTOM + "/raw", str( rawTemp ) )
			log( LOG_LEVEL_DEBUG, CHILD_DEVICE_TEMP, MSG_SUBTYPE_CUSTOM + "/corrected", str( correctedTemp ) )
			
			if abs( priorCorrected - correctedTemp ) >= TEMP_TOLERANCE:
				log( LOG_LEVEL_STATE, CHILD_DEVICE_TEMP, MSG_SUBTYPE_TEMPERATURE, str( currentTemp ) )	
				priorCorrected = correctedTemp	

		if bleEnabled and temp_ble_correct !=0 and bleCorrectEnabled:
				rawTemp = tempSensor.get_temperature( sensorUnits )
				corrected_temp = (rawTemp+temp_ble_correct)/2
				currentTemp = round( corrected_temp, 1 )
		currentLabel.text = "[b]" + str( currentTemp ) + scaleUnits + "[/b]"
		altCurLabel.text  = currentLabel.text

		dateLabel.text      = "[b]" + time.strftime("%d %b %a, %Y") + "[/b]"

		timeStr		 = time.strftime("%H:%M").lower()

		timeLabel.text      = ( "[b]" + ( timeStr if timeStr[0:1] != "0" else timeStr[1:] ) + "[/b]" ).lower()
		altTimeLabel.text  	= timeLabel.text

		change_system_settings()


# This is called when the desired temp slider is updated:

def update_set_temp( slider, value ):
	with thermostatLock:
		global setTemp
		priorTemp = setTemp
		setTemp = round( slider.value, 1 )
		setLabel.text = "  Set\n[b]" + str( setTemp ) + scaleUnits + "[/b]"
		if priorTemp != setTemp:
			log( LOG_LEVEL_STATE, CHILD_DEVICE_UICONTROL_SLIDER, MSG_SUBTYPE_TEMPERATURE, str( setTemp ) )


# Check the PIR motion sensor status

def check_pir( pin ):
	global minUITimer
	global lightOffTimer
	with thermostatLock:
		if GPIO.input( pirPin ): 
			log( LOG_LEVEL_INFO, CHILD_DEVICE_PIR, MSG_SUBTYPE_TRIPPED, "1" )

			if minUITimer != None:
				  Clock.unschedule( show_minimal_ui )
				  if lightOffTimer != None:
					Clock.unschedule( light_off )	
			minUITimer = Clock.schedule_once( show_minimal_ui, minUITimeout ) 
			lighOffTimer = Clock.schedule_once( light_off, lightOff )	
			ignore = False
			now = datetime.datetime.now().time()
			
			if pirIgnoreFrom > pirIgnoreTo:
				if now >= pirIgnoreFrom or now < pirIgnoreTo:
					ignore = True
			else:
				if now >= pirIgnoreFrom and now < pirIgnoreTo:
					ignore = True

			if screenMgr.current == "minimalUI" and not( ignore ):
				screenMgr.current = "thermostatUI"
				log( LOG_LEVEL_DEBUG, CHILD_DEVICE_SCREEN, MSG_SUBTYPE_TEXT, "Full" )
	
		else:
			log( LOG_LEVEL_DEBUG, CHILD_DEVICE_PIR, MSG_SUBTYPE_TRIPPED, "0" )

# connect with oregon scientific and check inside outside temperature
def ble_Check(dt):
	global ble_in
	if bleEnabled and ble_in.text != "None" :
		global bleTimer
		global setTemp
		global currentTemp
		global ble_out
		global temp_ble_correct
		global bluetoothImg
		global bluetoothMinImg
		with thermostatLock:
			print setTemp,currentTemp
			ble_in.text="None"
			ble_out.text="None"
			temp_ble_correct=0
			try:
				cmd = 'python blescan.py ' + settings.get( "ble" )[ "mac" ]
				p = subprocess32.Popen(cmd, stdout=subprocess.PIPE, shell=True)
				out, err = p.communicate(timeout=5) 
				result = out.split('\n')
				Clock.unschedule(bleTimer)
				if result[0] ==  "WeatherStation connected !":	
					try :
						line = result[1].translate(None, "()'")
						inTemperature= line.split(',')
						line = result[2].translate(None, "()'")
						outTemperature= line.split(',')
						in_temp = float(inTemperature[1])
						out_temp = float(outTemperature[1])
						if setTemp >= currentTemp +1 and GPIO.input( heatPin ) == False:
							bleTimer = Clock.schedule_once( ble_Check, bleTimeout_correct)
							bluetoothImg.color = (1,0,0,1)
							bluetoothMinImg.color = (1,0,0,0.4)
						else:
							bleTimer = Clock.schedule_once( ble_Check, bleTimeout)
							bluetoothImg.color = (1,1,1,1)
							bluetoothMinImg.color = (1,1,1,0.4)
						temp_ble_correct = in_temp
						ble_in.text = "\n".join( (
							"Temp in            : " +str(float(inTemperature[1])),
							"Temp in max   : " +str(float(inTemperature[2])),
							"Temp in min    : " +str(float(inTemperature[3])),
							"Temp out          : " +str(float(outTemperature[1])),
							"Temp out max : " +str(float(outTemperature[2])),
							"Temp out min  : " +str(float(outTemperature[3]))
							))
						ble_out.text = " ".join( (
							str(float(outTemperature[1])),
							))
						
					except:
						bluetoothImg.color = (1,1,1,0)
						bluetoothMinImg.color = (1,1,1,0)
						

						
			except:
				bluetoothImg.color = (1,1,1,0)
				bluetoothMinImg.color = (1,1,1,0)
				
				
			
# Minimal UI Display functions and classes
#shell.shell(has_input=False, record_output=True, record_errors=True, strip_empty=True)

def show_minimal_ui( dt ):
	with thermostatLock:
		screenMgr.current = "minimalUI"
		log( LOG_LEVEL_DEBUG, CHILD_DEVICE_SCREEN, MSG_SUBTYPE_TEXT, "Minimal" )

def light_off( dt ):
	with thermostatLock:
		GPIO.output( lightPin, GPIO.LOW )
		log( LOG_LEVEL_DEBUG, CHILD_DEVICE_SCREEN, MSG_SUBTYPE_TEXT, "Screen Off" )
		
class MinimalScreen( Screen ):
	def on_touch_down( self, touch ):
		if self.collide_point( *touch.pos ):
			touch.grab( self )
			return True

	def on_touch_up( self, touch ):
		global minUITimer
		global lightOffTimer
		if touch.grab_current is self:
			touch.ungrab( self )
			with thermostatLock:
				Clock.unschedule( light_off )
				if minUITimer != None:
					Clock.unschedule( show_minimal_ui )	
				minUITimer = Clock.schedule_once( show_minimal_ui, minUITimeout )
				lighOffTimer = Clock.schedule_once( light_off, lightOff )
				GPIO.output( lightPin, GPIO.HIGH )
				self.manager.current = "thermostatUI"
				log( LOG_LEVEL_DEBUG, CHILD_DEVICE_SCREEN, MSG_SUBTYPE_TEXT, "Full" )
			return True


##############################################################################
#                                                                            #
#       Kivy Thermostat App class                                            #
#                                                                            #
##############################################################################

class ThermostatApp( App ):

	def build( self ):
		global screenMgr

		# Set up the thermostat UI layout:
		thermostatUI = FloatLayout( size=( 800, 480 ) )

		# Make the background black:
		with thermostatUI.canvas.before:
			Color ( 0.0, 0.0, 0.0, 1 )
			self.rect = Rectangle( size=( 800, 480 ), pos=thermostatUI.pos )
			Color (1.0, 0.1,  0.1, 1.0)
			self.rect =Rectangle (size=(290,250), pos=(280,210))
			Color (0.0, 0.0,  0.0, 1)
			self.rect =Rectangle (size=(284,244), pos=(283,213))
		# Create the rest of the UI objects ( and bind them to callbacks, if necessary ):
		
		wimg = Image( source='web/images/logo.png' )
				
		heatControl.bind( on_press=control_callback )	
		holdControl.bind( on_press=control_callback )

		tempSlider.bind( on_touch_down=update_set_temp, on_touch_move=update_set_temp )

   	# set sizing and position info
		
		wimg.size = ( 80, 80 )
		wimg.size_hint = ( None, None )
		wimg.pos = ( 10, 390 )

		heatControl.size  = ( 100, 130 )
		heatControl.pos = ( 680, 280 )

		statusLabel.pos = ( 400, 300 )

		tempSlider.size  = ( 100, 360 )
		tempSlider.pos = ( 570, 20 )

		holdControl.size  = ( 100, 130 )
		holdControl.pos = ( 680, 80 )

		setLabel.pos = ( 590, 370 )
		
		bluetoothImg.pos = (730,0)

		currentLabel.pos = ( 400, 400 )

		dateLabel.pos = ( 180, 400 )
		timeLabel.pos = ( 170, 375 )
		
		
		weatherImg.pos = ( 355, 15 )
		weatherSummaryLabel.pos = ( 420, 15 )
		weatherDetailsLabel.pos = ( 480, 30 )
		
		versionLabel.pos = ( 710, -20 )
		
		forecastTodayHeading = Label( text="[b]OGGI[/b]", font_size='20sp', markup=True, size_hint = ( None, None ), pos = ( 80, 295 ) )
		
		forecastTodayImg.pos = ( 85, 195 )
		forecastTodaySummaryLabel.pos = ( 80, 260 )
		forecastTodayDetailsLabel.pos = ( 110, 200 )

		forecastTomoHeading = Label( text="[b]DOMANI[/b]", font_size='20sp', markup=True, size_hint = ( None, None ), pos = ( 80, 120 ) )

		forecastTomoImg.pos = ( 85, 20 )
		forecastTomoSummaryLabel.pos = ( 80, 100 )
		forecastTomoDetailsLabel.pos = ( 110, 25 )

		forecastNowHeading = Label( text="[b]ADESSO[/b]", font_size='20sp', markup=True, size_hint = ( None, None ), pos = ( 360, 120 ) )

		# Add the UI elements to the thermostat UI layout:
		thermostatUI.add_widget( wimg )
		thermostatUI.add_widget( heatControl )
		thermostatUI.add_widget( holdControl )
		thermostatUI.add_widget( tempSlider )
		thermostatUI.add_widget( currentLabel )
		thermostatUI.add_widget( setLabel )
		thermostatUI.add_widget( statusLabel )
		thermostatUI.add_widget( dateLabel )
		thermostatUI.add_widget( timeLabel )
		thermostatUI.add_widget( weatherImg )
		thermostatUI.add_widget( weatherSummaryLabel )
		thermostatUI.add_widget( weatherDetailsLabel )
		thermostatUI.add_widget( versionLabel )
		thermostatUI.add_widget( forecastTodayHeading )
		thermostatUI.add_widget( forecastTodayImg )
		thermostatUI.add_widget( forecastTodaySummaryLabel )
		thermostatUI.add_widget( forecastTodayDetailsLabel )
		thermostatUI.add_widget( forecastTomoHeading )
		thermostatUI.add_widget( forecastTomoImg )
		thermostatUI.add_widget( forecastTomoDetailsLabel )
		thermostatUI.add_widget( forecastTomoSummaryLabel )
		thermostatUI.add_widget( bluetoothImg )
		thermostatUI.add_widget( forecastNowHeading )
		layout = thermostatUI

		# Minimap UI initialization

		if minUIEnabled:
			uiScreen 	= Screen( name="thermostatUI" )
			uiScreen.add_widget( thermostatUI )

			minScreen 	= MinimalScreen( name="minimalUI" )
			minUI 		= FloatLayout( size=( 800, 480 ) )
			

			with minUI.canvas.before:
				Color( 0.0, 0.0, 0.0, 1 )
				self.rect = Rectangle( size=( 800, 480 ), pos=minUI.pos )

			if bleEnabled and ble_in.text != "None":
				ble_in.pos = (600,100)
				minUI.add_widget( ble_in )
				weatherminImg.pos = ( 450, 200 )
				weatherminSummaryLabel.pos = ( 590, 200 )
				minUI.add_widget(weatherminImg)
				minUI.add_widget(weatherminSummaryLabel)
				altCurLabel.pos = ( 190, 290 )
				altTimeLabel.pos = ( 170, 360 )
				altStatusLabel.pos = (160 , 170 )
				bluetoothMinImg.pos =(	210,340)
				minUI.add_widget(bluetoothMinImg)
			else:
				altCurLabel.pos = ( 390, 290 )
				altTimeLabel.pos = ( 335, 380 )
				altStatusLabel.pos = (360 , 170 )
				
			minUI.add_widget( altCurLabel )
			minUI.add_widget( altTimeLabel )
			minUI.add_widget( altStatusLabel )
			minScreen.add_widget( minUI )

			screenMgr = ScreenManager( transition=NoTransition())		# FadeTransition seems to have OpenGL bugs in Kivy Dev 1.9.1 and is unstable, so sticking with no transition for now
			screenMgr.add_widget ( uiScreen )
			screenMgr.add_widget ( minScreen )

			layout = screenMgr
			minUITimer = Clock.schedule_once( show_minimal_ui, minUITimeout )
			lighOffTimer = Clock.schedule_once( light_off, lightOff )
			if pirEnabled:
				Clock.schedule_interval( check_pir, pirCheckInterval )
			if bleEnabled:
				bleTimer = Clock.schedule_once( ble_Check, 4)

		# Start checking the temperature
		Clock.schedule_interval( check_sensor_temp, tempCheckInterval )

		# Show the current weather & forecast
		
		Clock.schedule_once( display_forecast_weather, 12 )
		Clock.schedule_once( display_current_weather, 10 )
		return layout


##############################################################################
#                                                                            #
#       Scheduler Implementation                                             #
#                                                                            #
##############################################################################

def startScheduler():
	log( LOG_LEVEL_INFO, CHILD_DEVICE_SCHEDULER, MSG_SUBTYPE_TEXT, "Started" )
	while True:
		if holdControl.state == "normal":
			with scheduleLock:
				log( LOG_LEVEL_DEBUG, CHILD_DEVICE_SCHEDULER, MSG_SUBTYPE_TEXT, "Running pending" )
				schedule.run_pending()

		time.sleep( 10 )


def setScheduledTemp( temp ):
	with thermostatLock:
		global setTemp
		if holdControl.state == "normal":
			setTemp = round( temp, 1 )
			setLabel.text = "  Set\n[b]" + str( setTemp ) + scaleUnits + "[/b]"
			tempSlider.value = setTemp
			log( LOG_LEVEL_STATE, CHILD_DEVICE_SCHEDULER, MSG_SUBTYPE_TEMPERATURE, str( setTemp ) )


def getTestSchedule():
	days = [ "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday" ]
	testSched = {}
	
	for i in range( len( days ) ):
		tempList = []
		for minute in range( 60 * 24 ):
			hrs, mins = divmod( minute, 60 )
			tempList.append( [
					str( hrs ).rjust( 2, '0' ) + ":" + str( mins ).rjust( 2, '0' ),
					float( i + 1 ) / 10.0 + ( ( 19.0 if tempScale == "metric" else 68.0 ) if minute % 2 == 1 else ( 22.0 if tempScale == "metric" else 72.0 ) )
					] )

		testSched[ days[i] ] = tempList

	return testSched


def reloadSchedule():
	with scheduleLock:
		schedule.clear()

		activeSched = None

		with thermostatLock:
			thermoSched = JsonStore( "thermostat_schedule.json" )
			if holdControl != "down" :
				if heatControl.state == "down":
					activeSched = thermoSched[ "heat" ]  
					log( LOG_LEVEL_INFO, CHILD_DEVICE_SCHEDULER, MSG_SUBTYPE_CUSTOM + "/load", "heat" )
			if useTestSchedule: 
				activeSched = getTestSchedule()
				log( LOG_LEVEL_INFO, CHILD_DEVICE_SCHEDULER, MSG_SUBTYPE_CUSTOM + "/load", "test" )
				print "Using Test Schedule!!!"
	
		if activeSched != None:
			for day, entries in activeSched.iteritems():
				for i, entry in enumerate( entries ):
					getattr( schedule.every(), day ).at( entry[ 0 ] ).do( setScheduledTemp, entry[ 1 ] )
					log( LOG_LEVEL_DEBUG, CHILD_DEVICE_SCHEDULER, MSG_SUBTYPE_TEXT, "Set " + day + ", at: " + entry[ 0 ] + " = " + str( entry[ 1 ] ) + scaleUnits )


##############################################################################
#                                                                            #
#       Web Server Interface                                                 #
#                                                                            #
##############################################################################

##############################################################################
#      encoding: UTF-8                                                       #
# Form based authentication for CherryPy. Requires the                       #
# Session tool to be loaded.                                                 #
##############################################################################
cherrypy.server.socket_host = '0.0.0.0'


SESSION_KEY = '_cp_username'

def check_credentials(username, password):
    """Verifies credentials for username and password.
    Returns None on success or a string describing the error on failure"""
    # Adapt to your needs
    if username in (settings.get( "thermostat" )[ "user" ]) and password == settings.get( "thermostat" )[ "pass" ]:
        return None
    else:
        return u"Incorrect username or password."
    
    # An example implementation which uses an ORM could be:
    # u = User.get(username)
    # if u is None:
    #     return u"Username %s is unknown to me." % username
    # if u.password != md5.new(password).hexdigest():
    #     return u"Incorrect password"

def check_auth(*args, **kwargs):
    """A tool that looks in config for 'auth.require'. If found and it
    is not None, a login is required and the entry is evaluated as a list of
    conditions that the user must fulfill"""
    conditions = cherrypy.request.config.get('auth.require', None)
    if conditions is not None:
        username = cherrypy.session.get(SESSION_KEY)
        if username:
            cherrypy.request.login = username
            for condition in conditions:
                # A condition is just a callable that returns true or false
                if not condition():
                    raise cherrypy.HTTPRedirect("/auth/login")
        else:
            raise cherrypy.HTTPRedirect("/auth/login")
    
cherrypy.tools.auth = cherrypy.Tool('before_handler', check_auth)

def require(*conditions):
    """A decorator that appends conditions to the auth.require config
    variable."""
    def decorate(f):
        if not hasattr(f, '_cp_config'):
            f._cp_config = dict()
        if 'auth.require' not in f._cp_config:
            f._cp_config['auth.require'] = []
        f._cp_config['auth.require'].extend(conditions)
        return f
    return decorate


# Conditions are callables that return True
# if the user fulfills the conditions they define, False otherwise
#
# They can access the current username as cherrypy.request.login
#
# Define those at will however suits the application.

def member_of(groupname):
    def check():
        # replace with actual check if <username> is in <groupname>
        return cherrypy.request.login == 'termo' and groupname == 'admin'
    return check

def name_is(reqd_username):
    return lambda: reqd_username == cherrypy.request.login

# These might be handy

def any_of(*conditions):
    """Returns True if any of the conditions match"""
    def check():
        for c in conditions:
            if c():
                return True
        return False
    return check

# By default all conditions are required, but this might still be
# needed if you want to use it inside of an any_of(...) condition
def all_of(*conditions):
    """Returns True if all of the conditions match"""
    def check():
        for c in conditions:
            if not c():
                return False
        return True
    return check


# Controller to provide login and logout actions

class AuthController(object):
    
    def on_login(self, username):
        """Called on successful login"""
    
    def on_logout(self, username):
        """Called on logout"""
    
    def get_loginform(self, username, msg="Login ", from_page="/"):
        
	file = open( "web/html/thermostat_login.html", "r" )

	html = file.read()

	file.close()
		
	return html %locals()
    
    
    @cherrypy.expose
    def login(self, username=None, password=None, from_page="/"):
        if username is None or password is None:
            return self.get_loginform("", from_page=from_page)
        
        error_msg = check_credentials(username, password)
        if error_msg:
            return self.get_loginform(username, error_msg, from_page)
        else:
            cherrypy.session[SESSION_KEY] = cherrypy.request.login = username
            self.on_login(username)
            raise cherrypy.HTTPRedirect(from_page or "/")
    
    @cherrypy.expose
    def logout(self, from_page="/"):
        sess = cherrypy.session
        username = sess.get(SESSION_KEY, None)
        sess[SESSION_KEY] = None
        if username:
            cherrypy.request.login = None
            self.on_logout(username)
        raise cherrypy.HTTPRedirect(from_page or "/")

#from auth import AuthController, require, member_of, name_is

class WebInterface(object):

	_cp_config = {
            'tools.sessions.on': True,
    	    'tools.auth.on': True
	    }
    
	auth = AuthController()
    

	@cherrypy.expose
	@require()
	def index( self ):	
		log( LOG_LEVEL_INFO, CHILD_DEVICE_WEBSERVER, MSG_SUBTYPE_TEXT, "Served thermostat.html to: " + cherrypy.request.remote.ip )	
		
		
		file = open( "web/html/thermostat.html", "r" )

		html = file.read()

		file.close()

		with thermostatLock:		

			html = html.replace( "@@version@@", str( THERMOSTAT_VERSION ) )
			html = html.replace( "@@temp@@", str( setTemp ) )
			html = html.replace( "@@current@@", str( currentTemp ) + scaleUnits )
			html = html.replace( "@@minTemp@@", str( minTemp ) )
			html = html.replace( "@@maxTemp@@", str( maxTemp ) )
			html = html.replace( "@@tempStep@@", str( tempStep ) )

		
			status = statusLabel.text.replace( "[b]", "<b>" ).replace( "[/b]", "</b>" ).replace( "\n", "<br>" ).replace( " ", "&nbsp;" )
			status = status.replace( "[color=00ff00]", '<font color="red">' ).replace( "[/color]", '</font>' ) 
	
			html = html.replace( "@@status@@", status )
			html = html.replace( "@@dt@@", dateLabel.text.replace( "[b]", "<b>" ).replace( "[/b]", "</b>" ) + ", " + timeLabel.text.replace( "[b]", "<b>" ).replace( "[/b]", "</b>" ) )
			html = html.replace( "@@heatChecked@@", "checked" if heatControl.state == "down" else "" )
			html = html.replace( "@@holdChecked@@", "checked" if holdControl.state == "down" else "" )
	
		return html


	@cherrypy.expose
	def set( self, temp, heat="off", fan="off", hold="off" ):
		global setTemp
		global setLabel
		global heatControl
		global fanControl

		log( LOG_LEVEL_INFO, CHILD_DEVICE_WEBSERVER, MSG_SUBTYPE_TEXT, "Set thermostat received from: " + cherrypy.request.remote.ip )	

		tempChanged = setTemp != float( temp )

		with thermostatLock:
			setTemp = float( temp )
			setLabel.text = "  Set\n[b]" + str( setTemp ) + "c[/b]"
			tempSlider.value = setTemp

			if tempChanged:
				log( LOG_LEVEL_STATE, CHILD_DEVICE_WEBSERVER, MSG_SUBTYPE_TEMPERATURE, str( setTemp ) )

			if heat == "on":
				setControlState( heatControl, "down" )
			else:
				setControlState( heatControl, "normal" )

			if fan == "on":
				setControlState( fanControl, "down" )
			else:
				setControlState( fanControl, "normal" )

			if hold == "on":
				setControlState( holdControl, "down" )
			else:
				setControlState( holdControl, "normal" )

			reloadSchedule()

		file = open( "web/html/thermostat_set.html", "r" )

		html = file.read()

		file.close()
		
		with thermostatLock:
			html = html.replace( "@@version@@", str( THERMOSTAT_VERSION ) )
			html = html.replace( "@@dt@@", dateLabel.text.replace( "[b]", "<b>" ).replace( "[/b]", "</b>" ) + ", " + timeLabel.text.replace( "[b]", "<b>" ).replace( "[/b]", "</b>" ) )
			html = html.replace( "@@temp@@", ( '<font color="red"><b>' if tempChanged else "" ) + str( setTemp ) + ( '</b></font>' if tempChanged else "" ) )
			html = html.replace( "@@heat@@", ( '<font color="red"><b>' if heat == "on" else "" ) + heat + ( '</b></font>' if heat == "on" else "" ) )
			html = html.replace( "@@fan@@",  ( '<font color="red"><b>' if fan == "on" else "" ) + fan + ( '</b></font>' if fan == "on" else "" ) )
			html = html.replace( "@@hold@@", ( '<font color="red"><b>' if hold == "on" else "" ) + hold + ( '</b></font>' if hold == "on" else "" ) )

		return html


	@cherrypy.expose
	def schedule( self ):	
		log( LOG_LEVEL_INFO, CHILD_DEVICE_WEBSERVER, MSG_SUBTYPE_TEXT, "Served thermostat_schedule.html to: " + cherrypy.request.remote.ip )			
		file = open( "web/html/thermostat_schedule.html", "r" )

		html = file.read()

		file.close()
		
		with thermostatLock:
			html = html.replace( "@@version@@", str( THERMOSTAT_VERSION ) )
			html = html.replace( "@@minTemp@@", str( minTemp ) )
			html = html.replace( "@@maxTemp@@", str( maxTemp ) )
			html = html.replace( "@@tempStep@@", str( tempStep ) )
		
			html = html.replace( "@@dt@@", dateLabel.text.replace( "[b]", "<b>" ).replace( "[/b]", "</b>" ) + ", " + timeLabel.text.replace( "[b]", "<b>" ).replace( "[/b]", "</b>" ) )
	
		return html

	@cherrypy.expose
	@cherrypy.tools.json_in()
	def save( self ):
		log( LOG_LEVEL_STATE, CHILD_DEVICE_WEBSERVER, MSG_SUBTYPE_TEXT, "Set schedule received from: " + cherrypy.request.remote.ip )	
		schedule = cherrypy.request.json

		with scheduleLock:
			file = open( "thermostat_schedule.json", "w" )

			file.write( json.dumps( schedule, indent = 4 ) )
		
			file.close()

		reloadSchedule()

		file = open( "web/html/thermostat_saved.html", "r" )

		html = file.read()

		file.close()
		
		with thermostatLock:
			html = html.replace( "@@version@@", str( THERMOSTAT_VERSION ) )
			html = html.replace( "@@dt@@", dateLabel.text.replace( "[b]", "<b>" ).replace( "[/b]", "</b>" ) + ", " + timeLabel.text.replace( "[b]", "<b>" ).replace( "[/b]", "</b>" ) )
		
		return html
		
	@cherrypy.expose
	def graph( self ):	
		log( LOG_LEVEL_INFO, CHILD_DEVICE_WEBSERVER, MSG_SUBTYPE_TEXT, "grah.html to: " + cherrypy.request.remote.ip )			
		file = open( "web/html/graph.html", "r" )

		html = file.read()

		file.close()
		
		return html

def startWebServer():	
	host = "discover" if not( settings.exists( "web" ) ) else settings.get( "web" )[ "host" ]
	#cherrypy.server.socket_host = host if host != "discover" else get_ip_address()	# use machine IP address if host = "discover"
	cherrypy.server.socket_port = 80 if not( settings.exists( "web" ) ) else settings.get( "web" )[ "port" ]

	log( LOG_LEVEL_STATE, CHILD_DEVICE_WEBSERVER, MSG_SUBTYPE_TEXT, "Starting on " + cherrypy.server.socket_host + ":" + str( cherrypy.server.socket_port ) )

	conf = {
		'/': {
			'tools.staticdir.root': os.path.abspath( os.getcwd() ),
			'tools.staticfile.root': os.path.abspath( os.getcwd() )
		},
		'/css': {
			'tools.staticdir.on': True,
			'tools.staticdir.dir': './web/css'
		},
		'/javascript': {
			'tools.staticdir.on': True,
			'tools.staticdir.dir': './web/javascript'
		},
		'/images': {
			'tools.staticdir.on': True,
			'tools.staticdir.dir': './web/images'
		},
		'/schedule.json': {
			'tools.staticfile.on': True,
			'tools.staticfile.filename': './thermostat_schedule.json'
		},
		'/favicon.ico': {
			'tools.staticfile.on': True,
			'tools.staticfile.filename': './web/images/favicon.ico'
		},
		'/graph': {
			'tools.staticdir.on': True,
			'tools.staticdir.dir': './web/graph'
		}

	}

	cherrypy.config.update(
		{ 'log.screen': debug,
		  'log.access_file': "",
		  'log.error_file': "",
		  'server.thread_pool' : 10  
		}
	)

	cherrypy.quickstart ( WebInterface(), '/', conf )	


##############################################################################
#                                                                            #
#       Main                                                                 #
#                                                                            #
##############################################################################

def main():
	# Start Web Server
	webThread = threading.Thread( target=startWebServer )
	webThread.daemon = True
	webThread.start()

	# Start Scheduler
	reloadSchedule()
	schedThread = threading.Thread( target=startScheduler )
	schedThread.daemon = True
	schedThread.start()

	# Start Thermostat UI/App
	ThermostatApp().run()


if __name__ == '__main__':
	try:
		main()
	finally:
		log( LOG_LEVEL_STATE, CHILD_DEVICE_NODE, MSG_SUBTYPE_CUSTOM + "/shutdown", "Thermostat Shutting Down..." )
		GPIO.cleanup()

		if logFile is not None:
			logFile.flush()
			os.fsync( logFile.fileno() )
			logFile.close()


