#!/usr/bin/python<br># -*- coding: utf-8 -*-
# Connect to Oregon Scientific BLE Weather Station
# Copyright (c) 2016 Arnaud Balmelle
#
# This script will connect to Oregon Scientific BLE Weather Station
# and retrieve the temperature of the base and sensors attached to it.
# If no mac-address is passed as argument, it will scan for an Oregon Scientific BLE Weather Station.
#
# Supported Oregon Scientific Weather Station: EMR211 and RAR218HG (and probably BAR218HG)
#
# Usage: python bleWeatherStation.py [mac-address]
#
# Dependencies:
# - Bluetooth 4.1 and bluez installed
# - bluepy library (https://github.com/IanHarvey/bluepy)
#
# License: Released under an MIT license: http://opensource.org/licenses/MIT
import sys
import logging
import time
#import json
#import sqlite3
from bluepy.btle import *
# uncomment the following line to get debug information
#logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG)
#WEATHERSTATION_NAME = "IDTW211R" # IDTW213R for RAR218H
class WeatherStation:
	def __init__(self, mac):
		self._data = {}
		try:
			self.p = Peripheral(mac, ADDR_TYPE_RANDOM)
			self.p.setDelegate(NotificationDelegate())
			print ('WeatherStation connected !')
		except BTLEException:
			self.p = 0
			print ('Connection to WeatherStation failed !') 
			
	def _enableNotification(self):
		try:
			# Enable all notification or indication
			self.p.writeCharacteristic(0x000c, "\x02\x00")
			self.p.writeCharacteristic(0x000f, "\x02\x00")
			self.p.writeCharacteristic(0x0012, "\x02\x00")
			self.p.writeCharacteristic(0x0015, "\x01\x00")
			self.p.writeCharacteristic(0x0018, "\x02\x00")
			self.p.writeCharacteristic(0x001b, "\x02\x00")
			self.p.writeCharacteristic(0x001e, "\x02\x00")
			self.p.writeCharacteristic(0x0021, "\x02\x00")
			self.p.writeCharacteristic(0x0032, "\x01\x00")
		
		except BTLEException as err:
			print(err)
			self.p.disconnect()
	
	def monitorWeatherStation(self):
		try:
			# Enable notification
			self._enableNotification()
			# Wait for notifications
			while self.p.waitForNotifications(1.0):
				# handleNotification() was called
				continue
		except:
			return None
		
		regs = self.p.delegate.getData()
		if regs is not None:
			# expand INDOOR_AND_CH1_TO_3_TH_DATA_TYPE0
			self._data['index0_temperature'] = ''.join(regs['data_type0'][4:6] + regs['data_type0'][2:4])
			self._data['index1_temperature'] = ''.join(regs['data_type0'][8:10] + regs['data_type0'][6:8])
			#self._data['index2_temperature'] = ''.join(regs['data_type0'][12:14] + regs['data_type0'][10:12])
			#self._data['index3_temperature'] = ''.join(regs['data_type0'][16:18] + regs['data_type0'][14:16])
			# expand INDOOR_AND_CH1_TO_3_TH_DATA_TYPE1
			self._data['index0_temperature_max'] = ''.join(regs['data_type1'][10:12] + regs['data_type1'][8:10])
			self._data['index0_temperature_min'] = ''.join(regs['data_type1'][14:16] + regs['data_type1'][12:14])
			self._data['index1_temperature_max'] = ''.join(regs['data_type1'][18:20] + regs['data_type1'][16:18])
			self._data['index1_temperature_min'] = ''.join(regs['data_type1'][22:24] + regs['data_type1'][20:22])
			#self._data['index2_temperature_max'] = ''.join(regs['data_type1'][26:28] + regs['data_type1'][24:26])
			#self._data['index2_temperature_min'] = ''.join(regs['data_type1'][30:32] + regs['data_type1'][28:30])
			#self._data['index3_temperature_max'] = ''.join(regs['data_type1'][34:36] + regs['data_type1'][32:34])
			#self._data['index3_temperature_min'] = ''.join(regs['data_type1'][38:40] + regs['data_type1'][36:38])
			return True
		else:
			return None
	
	def getIndoorTemp(self):
		if 'index0_temperature' in self._data:
			temp = int(self._data['index0_temperature'], 16) / 10.0
			max = int(self._data['index0_temperature_max'], 16) / 10.0
			min = int(self._data['index0_temperature_min'], 16) / 10.0
			print ("Indoor temp :" ,temp, max, min)
			return temp
		else:
			return None
	
	def getOutdoorTemp(self):
		if 'index1_temperature' in self._data:
			temp = int(self._data['index1_temperature'], 16) / 10.0
			max = int(self._data['index1_temperature_max'], 16) / 10.0
			min = int(self._data['index1_temperature_min'], 16) / 10.0
			print ("Outdoor temp :",temp, max, min)
			return temp
		else:
			return None
	
	def disconnect(self):
		self.p.disconnect()
		
class NotificationDelegate(DefaultDelegate):
	def __init__(self):
		DefaultDelegate.__init__(self)
		self._indoorAndOutdoorTemp_type0 = None
		self._indoorAndOutdoorTemp_type1 = None
		
	def handleNotification(self, cHandle, data):
		formatedData = binascii.b2a_hex(data)
		if cHandle == 0x0017:
			# indoorAndOutdoorTemp indication received
			if formatedData[0] == '8':
				# Type1 data packet received
				self._indoorAndOutdoorTemp_type1 = formatedData
			else:
				# Type0 data packet received
				self._indoorAndOutdoorTemp_type0 = formatedData
		else:
			# skip other indications/notifications
			pass  # No op function
	
	def getData(self):
			if self._indoorAndOutdoorTemp_type0 is not None:
				# return sensors data
				return {'data_type0':self._indoorAndOutdoorTemp_type0, 'data_type1':self._indoorAndOutdoorTemp_type1}
			else:
				return None
class ScanDelegate(DefaultDelegate):
	def __init__(self):
		DefaultDelegate.__init__(self)
		

if __name__=="__main__":
	weatherStationMacAddr = sys.argv[1]
	
	try:
		# Attempting to connect to device with MAC address "weatherStationMacAddr"
		weatherStation = WeatherStation(weatherStationMacAddr)
		if weatherStation.monitorWeatherStation() is not None:
			# WeatherStation data received
			indoor = weatherStation.getIndoorTemp()
			outdoor = weatherStation.getOutdoorTemp()
			weatherStation.disconnect()
		else:
			print('No data received from WeatherStation')
	
	except KeyboardInterrupt:
		print('Program stopped by user')