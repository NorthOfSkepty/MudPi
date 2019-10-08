import time
import json
import threading
from nanpy import (SerialManager)
from nanpy.serialmanager import SerialManagerError
from nanpy.sockconnection import (SocketManager, SocketManagerError)
import sys
sys.path.append('..')

import variables
import importlib

#r = redis.Redis(host='127.0.0.1', port=6379)

class ArduinoControlWorker():
	def __init__(self, config, main_thread_running, system_ready, connection=None):
		#self.config = {**config, **self.config}
		self.config = config
		self.main_thread_running = main_thread_running
		self.system_ready = system_ready
		self.node_ready = False

		if connection is not None:
			self.connection = connection
			self.controls = []
			self.init_controls()
			self.node_ready = True
		else:
			attempts = 3
			if self.config.get('use_wifi', False):
				while attempts > 0:
					try:
						attempts-= 1
						self.connection = SocketManager(host=str(self.config.get('address', 'mudpi.local')))
						self.controls = []
						self.init_controls()
					except SocketManagerError:
						print('[{name}] \033[1;33m Node Timeout\033[0;0m ['.format(**self.config), attempts, ' tries left]...')
						time.sleep(15)
						print('Retrying Connection...')
					else:
						print('[{name}] Wifi Connection \t\033[1;32m Success\033[0;0m'.format(**self.config))
						self.node_ready = True
						break
			else:
				while attempts > 0:
					try:
						attempts-= 1
						self.connection = SerialManager(device=str(self.config.get('address', '/dev/ttyUSB1')))
						self.controls = []
						self.init_controls()
					except SerialManagerError:
						print('[{name}] \033[1;33m Node Timeout\033[0;0m ['.format(**self.config), attempts, ' tries left]...')
						time.sleep(15)
						print('Retrying Connection...')
					else:
						print('[{name}] Serial Connection \t\033[1;32m Success\033[0;0m'.format(**self.config))
						self.node_ready = True
						break
		
		return

	def dynamic_import(self, path):
		components = path.split('.')

		s = ''
		for component in components[:-1]:
			s += component + '.'

		parent = importlib.import_module(s[:-1])
		sensor = getattr(parent, components[-1])

		return sensor

	def init_controls(self):
		for control in self.config['controls']:
			if control.get('type', None) is not None:
				#Get the control from the controls folder {control name}_control.{ControlName}Control
				control_type = 'controls.arduino.' + control.get('type').lower() + '_control.' + control.get('type').capitalize() + 'Control'
				
				analog_pin_mode = False if control.get('is_digital', False) else True

				imported_control = self.dynamic_import(control_type)
				#new_control = imported_control(control.get('pin'), name=control.get('name', control.get('type')), connection=self.connection, key=control.get('key', None))
				
				# Define default kwargs for all control types, conditionally include optional variables below if they exist
				control_kwargs = { 
					'name' : control.get('name', control.get('type')),
					'pin' : control.get('pin'),
					'connection': self.connection,
					'key'  : control.get('key', None),
					'analog_pin_mode': analog_pin_mode,
					'topic': control.get('topic', None)
				}

				# optional control variables 
				# add conditional control vars here...

				new_control = imported_control(**control_kwargs)

				new_control.init_control()
				self.controls.append(new_control)
				print('{type} Control {pin}...\t\t\t\033[1;32m Ready\033[0;0m'.format(**control))
		return

	def run(self):
		if self.node_ready:
			t = threading.Thread(target=self.work, args=())
			t.start()
			print(str(self.config['name']) +' Node Worker [' + str(len(self.config['controls'])) + ' Controls]...\t\033[1;32m Running\033[0;0m')
			return t
		else:
			print("Node Connection...\t\t\t\033[1;31m Failed\033[0;0m")
			return None

	def work(self):

		while self.main_thread_running.is_set():
			if self.system_ready.is_set() and self.node_ready:
				message = {'event':'ControlUpdate'}
				readings = {}
				for control in self.controls:
					result = control.read()
					readings[control.key] = result
					#r.set(sensor.get('key', sensor.get('type')), value)
					
				message['data'] = readings
				variables.r.publish('controls', json.dumps(message))
			#Will this nuke the connection?	
			time.sleep(0.5)
		#This is only ran after the main thread is shut down
		print("{name} Node Worker Shutting Down...\t\t\033[1;32m Complete\033[0;0m".format(**self.config))