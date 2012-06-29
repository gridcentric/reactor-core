#!/usr/bin/make -f

all: image_data.py
.PHONY: all

image_data.py: image.py $(wildcard *.png)
	@python image.py $(wildcard *.png)

clean:
	@rm -f image_data.py *.pyc
.PHONY: clean
