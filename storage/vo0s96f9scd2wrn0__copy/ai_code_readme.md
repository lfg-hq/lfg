# Calculator App Documentation

## Overview
This is a simple, yet fully functional web-based calculator application built with HTML, CSS, and JavaScript. The calculator supports basic arithmetic operations and provides a clean, responsive user interface.

## Features
- Basic arithmetic operations: addition, subtraction, multiplication, division
- Clear function (AC) to reset calculations
- Delete function (DEL) to remove the last entered digit
- Decimal point input support
- Error handling for division by zero
- Responsive design for different screen sizes
- Keyboard support for improved usability

## Project Structure
- `index.html`: Main HTML structure of the calculator
- `styles.css`: Styling for the calculator interface
- `script.js`: Calculator logic and functionality

## Implementation Details

### HTML Structure
The calculator is structured as a grid layout with:
- Display area (showing previous and current operands)
- Operation buttons (AC, DEL, +, -, ×, ÷)
- Number buttons (0-9 and decimal point)
- Equals button

### CSS Styling
- Modern gradient background
- Glass-effect styling for the calculator body
- Responsive design that works on mobile devices
- Visual feedback for button interactions
- Different color schemes for different button types

### JavaScript Functionality
- `Calculator` class that encapsulates all calculator operations
- Methods for handling various calculator functions:
  - `clear()`: Resets the calculator
  - `delete()`: Removes the last digit
  - `appendNumber()`: Adds a number to the display
  - `chooseOperation()`: Sets the current operation
  - `compute()`: Performs the calculation
  - `updateDisplay()`: Updates the UI
  - `handleKeyboardInput()`: Processes keyboard events

### Key Components

#### Number Formatting
The calculator properly formats numbers with thousands separators and handles decimal places appropriately.

#### Error Handling
Division by zero is caught and displays an alert to the user.

#### Keyboard Support
The calculator can be operated using the keyboard:
- Numbers 0-9 for numeric input
- `.` for decimal point
- `+`, `-`, `*`, `/` for operations
- `Enter` or `=` to compute results
- `Backspace` to delete
- `Escape` to clear all

## Usage
1. Open the `index.html` file in any web browser
2. Use the calculator by clicking on the buttons or using keyboard shortcuts
3. The top display shows the previous operand and current operation
4. The bottom display shows the current number being entered or the result

## Future Enhancements
Potential improvements that could be added:
- Scientific calculator functions
- History of calculations
- Memory functions (M+, M-, MR, MC)
- Percentage calculations
- Dark/light theme toggle
