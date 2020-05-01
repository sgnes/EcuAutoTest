## EcuAutoTest

A tool which can control ECU(Electronic Control Unit) for testing automation, like for CAN signal test, UDS service test...

## What this tool can do?

* Change ECU calibration/global variable 
* Measure ECU global variable
* Send CAN message to CAN bus
* Receive CAN signals from CAN bus

## How is this tool will work

This tool use the Windows COM interface to control the Vector CANalyzer and CANape to control and measure the ECU, also python-udsoncan  is integrated for UDS testing.

Just like the manually test:

1. for testing ECU RX signals, this tool can control the CANalyzer and send the specific CAN signal, and check the corresponding ECU variable value via controlling the CANape;
2. for testing ECU TX signals, this tool  can control the CANape to change some ECU calibration/global variable to change the TX CAN signals, then check the corresponding CAN signals value via CANalyzer;
3. for UDS testing and other test, similar to CAN signals test;



## How to use this tool

1.  clone from git: https://github.com/sgnes/EcuAutoTest;
2. create a CANalyzer project;
3. create a CANape project;
4. generate the needed CAPL script(if you need to send CAN message to CAN bus);
5. write your test case and project configuration in excel file;
6. run the script

## CAPL script

Because Vector CANalyzer doesn't support send CAN signals via Windows COM, so if needed, user has to write CAPL script to send the needed CAN messages;

Normally this CAPL script can be generated by writing a script, which load the dbc file(CAN database), and generate the CAPL script, you can use [canmatrix](https://github.com/ebroecker/canmatrix) if use python script to parse the dbc file.

## How to write project configuration 

## How to write test case

## Limitation

1. For now only support Vector CANalyzer/CANape, no support for other tools, like INCA;

   

## Issue feedback

1. you can create a issue in this project;
2. or send email to sgnes0514@gmail.com
