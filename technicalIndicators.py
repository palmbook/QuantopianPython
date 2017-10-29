# Quotes is a list of list where each list is in format
#
#        0             1        2     3    4     5     6      7
# [ market name, ticker name, date, open, high, low, close, volume ]

import numpy as np

def averageTrueRange(quotes):
	# Calculate true range for each period
	tr = []
	for i in range(1, len(quotes)):
		tr.append(trueRange(quotes[i-1:i+1]))
		
	return np.mean(tr)

def simpleMovingAverage(quotes):
	close = [item[6] for item in quotes]
	return np.mean(close)

def trueRange(quotes):
	# Check that we have only 2 quotes
	assert len(quotes) == 2
	
	m1 = quotes[1][4] - quotes[1][5]
	m2 = quotes[1][4] - quotes[0][6]
	m3 = quotes[1][5] - quotes[0][6]
	
	return max(abs(m1), abs(m2), abs(m3))
