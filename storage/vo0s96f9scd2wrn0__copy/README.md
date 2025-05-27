# Calculator App Documentation

## Overview
This is a modern, responsive calculator web application that provides both standard arithmetic functionality and binary operations with an attractive user interface. The calculator features a clean design with a glass-effect styling and supports both mouse and keyboard inputs.

## Features

### Standard Calculator
- Basic arithmetic operations (addition, subtraction, multiplication, division)
- Clear function (AC) to reset the calculator
- Delete function (DEL) to remove the last entered digit
- Decimal point input support
- Error handling for division by zero
- Visual display of both current input and previous operations

### Binary Calculator
- Mode switching between standard and binary calculators
- Binary number input (0 and 1 only)
- Decimal to Binary conversion
- Binary to Decimal conversion
- Bitwise operations: AND, OR, XOR, NOT
- Bit shift operations: Left shift (<<), Right shift (>>)
- Visual display of binary operations

## Technical Implementation

### HTML (index.html)
- Structured layout using semantic HTML5
- Separate button layouts for standard and binary modes
- Mode switching interface

### CSS (styles.css)
- Modern design with gradient background
- Glass-effect styling with backdrop filter
- Responsive layout with media queries
- Visual feedback on button interactions
- Color-coded buttons for different functions

### JavaScript (script.js)
- Object-oriented approach with separate Calculator and BinaryCalculator classes
- Methods for all calculator operations
- Binary operations implementation with proper error handling
- Mode switching logic
- Event listeners for both button clicks and keyboard inputs
- Proper number formatting with locale support
- State management for calculator operations

## How to Use

### Mode Switching
- Click "Standard" for basic arithmetic operations
- Click "Binary" for binary operations and conversions

### Standard Calculator
#### Mouse Controls
- Click number buttons (0-9) to input values
- Click operation buttons (+, -, ×, ÷) to select operations
- Click equals (=) to compute results
- Click AC to clear all values
- Click DEL to remove the last digit

#### Keyboard Controls
- Numbers 0-9 for numeric input
- "." for decimal point
- "+", "-", "*", "/" for operations
- "Enter" or "=" to compute results
- "Backspace" to delete
- "Escape" to clear all

### Binary Calculator
#### Mouse Controls
- Click binary number buttons (0, 1) to input values
- Click operation buttons (AND, OR, XOR, NOT, etc.) to select operations
- Click "DEC→BIN" to convert decimal to binary
- Click "BIN→DEC" to convert binary to decimal
- Click equals (=) to compute results
- Click AC to clear all values
- Click DEL to remove the last digit

#### Keyboard Controls (in Binary Mode)
- "0" and "1" for binary input
- "Enter" or "=" to compute results
- "Backspace" to delete
- "Escape" to clear all

## Installation
1. Create three files: index.html, styles.css, and script.js
2. Copy the provided code into each file
3. Open index.html in any web browser