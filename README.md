# BlitzPlayer

BlitzPlayer is a lightweight media player built with **Python (PyQt6)** and powered by the **mpv engine**.  
It features a modern dark UI, supports local file playback, and allows streaming via URL.

## Features
- Play local video & audio files  
- Stream from online URLs  
- Skip backward / skip forward controls  
- Play / Pause button (white themed)  
- Dark, modern user interface  
- Menu options: **Open File, Open URL, About, Exit**  
- Cross-platform support (Windows & Linux when run from source)  

## Requirements
- Python **3.10+**  
- [mpv player](https://mpv.io/) installed and available in your PATH  
- Install dependencies:
  ```bash
  pip install pyqt6 python-mpv
  ```

## Running from Source
This repository contains **only the source code** (no setup files provided).  

1. Clone the repository:
   ```bash
   git clone https://github.com/Max6079/BlitzPlayer.git
   cd BlitzPlayer
   ```

2. Run the application:
   ```bash
   python blitzplayer.py
   ```

## Notes
- No prebuilt setup or executables are included.  
- If you want to package BlitzPlayer into a standalone app, use tools like **PyInstaller** or **cx_Freeze**.  

## Project Info
- **Version:** 1.0  
- **Creator:** Gaurav Patil  
- **Contributors:** Dinesh Ade, Atharva Raul  
