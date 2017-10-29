#!/usr/bin/env python
# -*- coding: utf-8 -*-
#

########################### PORTFOLIO #####################################
#
# Implementing Quantopian-like engine on local computer
# Data is queried from Google Finance (Deprecated)
# But can be used with other sources as well
#
# VERSION: 0.2 BETA
#
# github.com/palmbook
###########################################################################

import datetime
import random

import GoogleFinanceEndDay

# Sample technical indicators
# Should be replaced with something else
import technicalIndicators as ti

from bokeh.layouts import gridplot
from bokeh.plotting import figure, show, output_file

###### NOTE! bokeh.charts was deprecated, will be temporarily removed
#from bokeh.charts import Area

from bokeh.models import NumeralTickFormatter

import threading
from threading import Thread
from functools import partial

mode = 'backtest' # Can be 'backtest', 'optimize', 'optimize_and_forwardtest', or 'online'

# Initial Values
interval = '1d'
initial_cash = 1000000
stocks = []
benchmark = []
skip = 100 # skip the first 50 quotes, we need these for calculations

# Verbose Flag
verbose = True

# Config for multi-threading
num_threads = 4
thread_started = False
lock = threading.Lock()

###### GLOBAL VARIABLES
########## DO NOT EDIT

# quotes
#
# Structure: dict of [quotes, pos]
quotes = dict()

# benchmark_quotes
benchmark_quotes = dict()

# runtime tracking
positions = dict()
currentdate = datetime.datetime.today()
benchmark_value = initial_cash
portfolio_value = initial_cash
cash = initial_cash


# Trackers
port_value_over_time = []
benchmark_value_over_time = []
position_over_time = dict()

# Storages for multi-threading methods
score_list = []
positions_thread = dict()
portfolio_value_thread = dict()
cash_thread = dict()
port_value_over_time_thread = dict()
position_over_time_thread = dict()
lastActive = currentdate




################## DO NOT EDIT THIS PART ###########################
# 
# The part to implement your algorithm is at the end of this file
# Please scroll past this section
#
####################################################################




# Function for outputing messages
#
# TODO: Colorize!
# TODO: Refactoring the code, so multi-threading does not
#       require separate methods

def stdout(explanation, lvl='INFO'):
	print lvl + " : " + explanation

# Perform a little bit of self check
def selftest():

	# We should have some money to start with
	assert initial_cash >= 1000
	
	# We only support day/week/month
	assert (interval == '1d') or (interval == '1w') or (interval == '1m')

# Set initial cash

def setCash(c):
	initial_cash = c
	selftest()

# Set interval
	
def setInterval(i):
	interval = i
	selftest()

# Function to convert end-day to weekly data
	
def dtow(pricelist):
	start = 0
	d,o,h,l,c, v = 0,0,0,0,0, 0
	
	tquotelist = []
	
	for q in pricelist:
		if q[2].isocalendar()[1] != start:
			# New week
			
			# Write old week
			if start > 0:
				tquotelist.append([q[0], q[1], d, o, h, l, c, v])
				d,o,h,l,c,v = 0,0,0,0,0,0
			
			d = q[2]
			o = q[3]
			h = q[4]
			l = q[5]
			c = q[6]
			v = q[7]
			
			start = q[2].isocalendar()[1]
		else:
			# Continue
			
			if q[4] > h:
				h = q[4]
			if q[5] < l:
				l = q[5]
			c = q[6]
			v += q[7]

	tquotelist.append([q[0], q[1], d, o, h, l, c, v])

	return tquotelist
	
# Load data from Google Finance
	
def populateData():
	for stock in stocks:
		if interval == '1d':
			# Get data from Google Finance
			stdout('Populating quotes for ' + str(stock[0:2]))
			quotelist = GoogleFinanceEndDay.retrieveAll([stock[0],stock[1]])
			
			# Put the quotes into the dictionary along with current position (0) and commission fee
			quotes[str(stock[0:2])] = [quotelist, 0, stock[2]]
		elif interval == '1w':
			# Get data from Google Finance
			stdout('Populating quotes for ' + str(stock[0:2]))
			quotelist = GoogleFinanceEndDay.retrieveAll([stock[0],stock[1]])
			
			# Convert to 1w interval
			tquotelist = dtow(quotelist)
			
			# Put the quotes into the dictionary along with current position (0) and commission fee
			quotes[str(stock[0:2])] = [tquotelist, 0, stock[2]]
		
		# Initialize position
		positions[str(stock[0:2])] = 0
	
	for stock in benchmark:
		if interval == '1d':
			# Get data from Google Finance
			stdout('Populating benchmark quotes for ' + str(stock[0:2]))
			quotelist = GoogleFinanceEndDay.retrieveAll([stock[0],stock[1]])
			
			# Put the quotes into the dictionary along with current position (0) and weight
			benchmark_quotes[str(stock[0:2])] = [quotelist, 0, stock[2]]
	
	for key in positions.keys():
		position_over_time[key] = []
	
	position_over_time['cash'] = []
	position_over_time['date'] = []
	

# Get a list of quotes
def getQuotes(key, count = 0):
	assert count >= 0
	
	if count == 0:
		# Get all
		if quotes[key][0][quotes[key][1]][2] > currentdate:
			return quotes[key][0][0:quotes[key][1]]
		else:
			return quotes[key][0][0:quotes[key][1]+1]
	if quotes[key][0][quotes[key][1]][2] > currentdate:
		return quotes[key][0][quotes[key][1]-count:quotes[key][1]]
	else:
		return quotes[key][0][quotes[key][1]+1-count:quotes[key][1]+1]

# Get the current quote
def getCurrent(key):
	if quotes[key][0][quotes[key][1]][2] > currentdate:
		return quotes[key][0][quotes[key][1]-1]
	else:
		return quotes[key][0][quotes[key][1]]

# Calculate the return of benchmark for a given period
		
def getBenchmarkChange(key):
	if benchmark_quotes[key][0][benchmark_quotes[key][1]][2] > currentdate:
		return benchmark_quotes[key][0][benchmark_quotes[key][1]-1][6]/benchmark_quotes[key][0][benchmark_quotes[key][1]-2][6]
	else:
		return benchmark_quotes[key][0][benchmark_quotes[key][1]][6]/benchmark_quotes[key][0][benchmark_quotes[key][1]-1][6]

# Update the value of benchmark
# Should be called each interval

def updateBenchmarkValue():
	global benchmark_value
	dailyAggChange = 0.00
	for key in benchmark_quotes.keys():
		dailyAggChange = dailyAggChange + (getBenchmarkChange(key) * benchmark_quotes[key][2])
	benchmark_value = benchmark_value * dailyAggChange
	
	benchmark_value_over_time.append([currentdate, benchmark_value])
	if verbose:
		stdout('Benchmark Value: ' + str(benchmark_value), 'DEBUG')

# Update the total portfolio value
# Should be called each interval

def updatePortfolioValue():
	global portfolio_value
	portfolio_value = cash
	for key in positions.keys():
		portfolio_value = portfolio_value + (getPosition(key) * getCurrent(key)[6])
		position_over_time[key].append(getPosition(key) * getCurrent(key)[6])
	position_over_time['cash'].append(cash)
	position_over_time['date'].append(currentdate)
	
	port_value_over_time.append([currentdate, portfolio_value])
	
	if verbose:
		stdout('Portfolio Value: ' + str(portfolio_value), 'DEBUG')
		
	updateBenchmarkValue()

# Get the commission fee

def getCommission(key):
	return quotes[key][2]/100.00	

# Inquire existing position

def getPosition(key):
	return positions[key]
	
# Add position to a stock

def addPosition(key, volume):
	global cash
	positions[key] = positions[key] + volume
	cash = cash - (volume * getCurrent(key)[6]) - (volume * getCurrent(key)[6] * getCommission(key)) 
	
	if verbose:
		stdout(str(currentdate) + ' : Adding ' + str(volume) + ' shares to ' + str(key), 'DEBUG')
		
# Sell-off some position

def sellPosition(key, volume):
	global cash
	positions[key] = positions[key] - volume
	cash = cash + (volume * getCurrent(key)[6]) - (volume * getCurrent(key)[6] * getCommission(key)) 
	if verbose:
		stdout(str(currentdate) + ' : Selling ' + str(volume) + ' shares to ' + str(key), 'DEBUG')
		
# Add a stock to the list
	
def addStock(market, ticker, commission):
	stocks.append([market, ticker, commission])

# Add benchmark 

def addBenchmark(market, ticker, weight):
	benchmark.append([market, ticker, weight])

# Compute amount for a transaction

def expectedQuantity(key, value):
	return int(value/getCurrent(key)[6])

# Order as a percentage of portfolio value
def order_percent(key, percent):
	value = portfolio_value * percent
	if verbose:
		stdout('New value for ' + str(key) + ' is ' + str(value), 'DEBUG')

	newposition = expectedQuantity(key, value)
	if verbose:
		stdout('New position for ' + str(key) + ' is ' + str(newposition), 'DEBUG')
	
	if verbose:
		stdout('Existing position for ' + str(key) + ' is ' + str(getPosition(key)), 'DEBUG')
		
	diff = newposition - getPosition(key)
	
	if diff > 0:
		if diff * getCurrent(key)[6] > cash:
			addPosition(key, expectedQuantity(key, cash))
		else:
			addPosition(key, diff)
	else:
		sellPosition(key, abs(diff))
		



############### METHODS FOR MULTI-THREADING #########################################
# These are thread-safe methods to run optimizer
######################################################################################

def initThreadStorage(param):
	# initialize each variable
	for p in param:
		positions_thread[str(p)] = dict()
		for stock in stocks:
			positions_thread[str(p)][str(stock[0:2])] = 0
		portfolio_value_thread[str(p)] = initial_cash
		cash_thread[str(p)] = initial_cash
		port_value_over_time_thread[str(p)] = []
		position_over_time_thread[str(p)] = dict()
		for stock in stocks:
			position_over_time_thread[str(p)][str(stock[0:2])] = []
		position_over_time_thread[str(p)]['date'] = []
		position_over_time_thread[str(p)]['cash'] = []


def updatePortfolioValue_thread(threadID):
	with lock:
		portfolio_value_thread[threadID] = cash_thread[threadID]
		for key in positions_thread[threadID].keys():
			portfolio_value_thread[threadID] = portfolio_value_thread[threadID] + (getPosition_thread(key, threadID) * getCurrent(key)[6])
			position_over_time_thread[threadID][key].append(getPosition_thread(key, threadID) * getCurrent(key)[6])
		position_over_time_thread[threadID]['cash'].append(cash_thread[threadID])
		position_over_time_thread[threadID]['date'].append(currentdate)
		
		port_value_over_time_thread[threadID].append([currentdate, portfolio_value_thread[threadID]])

def getPosition_thread(key, threadID):
	return positions_thread[threadID][key]

def addPosition_thread(key, volume, threadID):
	with lock:
		positions_thread[threadID][key] = positions_thread[threadID][key] + volume
		cash_thread[threadID] = cash_thread[threadID] - (volume * getCurrent(key)[6]) - (volume * getCurrent(key)[6] * getCommission(key))

def sellPosition_thread(key, volume, threadID):
	with lock:
		positions_thread[threadID][key] = positions_thread[threadID][key] - volume
		cash_thread[threadID] = cash_thread[threadID] + (volume * getCurrent(key)[6]) - (volume * getCurrent(key)[6] * getCommission(key))

# Order as a percentage of portfolio value
# This is thread-safe version

def order_percent_thread(key, percent, threadID):
	with lock:
		value = portfolio_value_thread[threadID] * percent

	newposition = expectedQuantity(key, value)
		
	diff = newposition - getPosition_thread(key, threadID)
	
	if diff > 0:
		if diff * getCurrent(key)[6] > cash:
			addPosition_thread(key, expectedQuantity(key, cash), threadID)
		else:
			addPosition_thread(key, diff, threadID)
	else:
		sellPosition_thread(key, abs(diff), threadID)

######################## END MULTI-THREAD ##########################################

# Move position index of each quote to a correct position
def adjustIndex():
	for key in quotes.keys():
		while quotes[key][1] < len(quotes[key][0]) - 1:
			if quotes[key][0][quotes[key][1]][2] < currentdate:
				quotes[key][1] = quotes[key][1] + 1
			else:
				break
				
	for key in benchmark_quotes.keys():
		while benchmark_quotes[key][1] < len(benchmark_quotes[key][0]) - 1:
			if benchmark_quotes[key][0][benchmark_quotes[key][1]][2] < currentdate:
				benchmark_quotes[key][1] = benchmark_quotes[key][1] + 1
			else:
				break

def runForwardtest(algoMethod):
	global currentdate
	
	# Set current date to latest first date of series
	currentdate = max([quotes[key][0][0][2] for key in quotes.keys()]) + datetime.timedelta(days = skip)
	
	# Start forward test
	# Do it period-by-period
	
	while currentdate <= datetime.datetime.today():
		# Boolean variable to check if today is a trading day
		active = False
		
		# Adjust index
		adjustIndex()
		
		# If the date of the quote matches today's date, execute algo
		for key in quotes.keys():
			if quotes[key][0][quotes[key][1]][2] == currentdate:
				algoMethod(key)
				active = True
		
		# Update portfolio value
		if active:
			updatePortfolioValue()
		
		# Shift to next day
		currentdate = currentdate + datetime.timedelta(days = 1)
	
	# Display Statistics
	
	if verbose:
		print port_value_over_time
		print benchmark_value_over_time
	
	p1 = figure(x_axis_type="datetime", title="Portfolio Value")
	p1.grid.grid_line_alpha=0.3
	p1.xaxis.axis_label = 'Date'
	p1.yaxis.axis_label = 'Value'

	p1.line([item[0] for item in port_value_over_time], [item[1] for item in port_value_over_time], color='#A6CEE3', legend='Algorithm')
	p1.line([item[0] for item in benchmark_value_over_time], [item[1] for item in benchmark_value_over_time], color='#B2DF8A', legend='Benchmark')
	p1.legend.location = "top_left"
	
	p1.yaxis[0].formatter = NumeralTickFormatter(format="$0")
	
	#area = Area(position_over_time, x='date', y=position_over_time.keys().remove('date'),title="Allocation", legend="top_left", stack=True,
        #    xlabel='Date', ylabel='Value')
	#area.yaxis[0].formatter = NumeralTickFormatter(format="$0")

	output_file("stocks.html", title="Performance Charts")

	#show(gridplot([[p1],[area]], plot_width=1376, plot_height=350))  # open a browser
        show(gridplot([[p1]], plot_width=1376, plot_height=350))  # open a browser

# Spawn threads for optimizer

def spawnThread(algoFunc, params):
	global lastActive
	
	if verbose:
		stdout('Thread ' + str(params) + ' is starting for date ' + str(currentdate))
	
	# Boolean variable to check if today is a trading day
	active = False
	
	# If the date of the quote matches today's date, execute algo
	for key in quotes.keys():
		if quotes[key][0][quotes[key][1]][2] == currentdate:
			algoFunc(key, params, partial(order_percent_thread, threadID = str(params)))
			active = True
		
	# Update portfolio value
	if active:
		updatePortfolioValue_thread(str(params))
		with lock:
			lastActive = currentdate

	if verbose:
		stdout('Thread ' + str(params) + ' is exiting for date ' + str(currentdate))
	
# Find an optimal set of parameters
# This will not do forward testing

def optimize(algoFunc, listOfParameters):
	global currentdate
	
	# Set current date to latest first date of series
	currentdate = max([quotes[key][0][0][2] for key in quotes.keys()]) + datetime.timedelta(days = skip)
	
	# Start forward test
	# Do it period-by-period
	
	while currentdate <= datetime.datetime.today():
		
		
		# Adjust index
		adjustIndex()
		
		threads_list = []
		
		# For each set of parameters, create a new thread
		for params in listOfParameters:
			threads_list.append(Thread(target=spawnThread, args=(algoFunc, params)))
		
		# Start threads and join
		for thread_set in [threads_list[i:i+num_threads] for i in range(0, len(threads_list), num_threads)]:
			for t in thread_set:
				t.start()
			
			for t in thread_set:
				t.join()
		
		if lastActive == currentdate:
			updateBenchmarkValue()
		
		# Shift to next day
		currentdate = currentdate + datetime.timedelta(days = 1)
		
	for key in port_value_over_time_thread.keys():
		print '****************************************************************'
		print port_value_over_time_thread[key]
	
	p1 = figure(x_axis_type="datetime", title="Portfolio Value")
	p1.grid.grid_line_alpha=0.3
	p1.xaxis.axis_label = 'Date'
	p1.yaxis.axis_label = 'Value'

	for param in listOfParameters:
		p1.line([item[0] for item in port_value_over_time_thread[str(param)]], [item[1] for item in port_value_over_time_thread[str(param)]], color='#' + ''.join([random.choice('0123456789ABCDEF') for x in range(6)]),legend=str(param))
		
	p1.line([item[0] for item in benchmark_value_over_time], [item[1] for item in benchmark_value_over_time], color='#B2DF8A', legend='Benchmark')
	p1.legend.location = "top_left"
	
	p1.yaxis[0].formatter = NumeralTickFormatter(format="$0")

	output_file("stocks.html", title="Performance Charts")

	show(gridplot([[p1]], plot_width=1376, plot_height=700))  # open a browser






############## USER IMPLEMENTATION SECTION #############################

# The actual trading algorithm
#
# Use the following functions
# setPositionPercent(key, percent) - To set your position for a stock to a particular percentage of port value

def runAlgorithm(key, params = [], setPositionPercent = order_percent):
	ratio = 1.00/len(quotes.keys())
	sma = ti.simpleMovingAverage(getQuotes(key, 14))
	if getCurrent(key)[6] > sma:
		setPositionPercent(key, ratio)
	else:
		setPositionPercent(key, 0)

# Objective Function for forward optimization

def score(param, pricequotes):
	return 0
		
# Initialize
# Add stocks and benchmark
# Then populate dat

def init():
	addBenchmark('INDEXBKK','SET',1)
	addStock('BKK', 'ADVANC', 0.15)
	addStock('BKK', 'PTT', 0.15)
	populateData()
	pass

# Initialize before optimization
# Set the number of threads
# Use this to prepare a list of parameters to be passed in
#
# Format: [[param set 1], [param set 2], ..., [param set n]]
def init_opt():
	global num_threads
	
	num_threads = 4
	
	param = []
	for num in range(5, 41):
		param.append([num])
		
	initThreadStorage(param)
	
	return param


if __name__ == "__main__":

	init()
	if mode == 'backtest':
		runForwardtest(runAlgorithm)
	elif mode == 'optimize':
		optimize(runAlgorithm, init_opt())
