# 🪄 PC Automation

**HPM Package for Hecos v0.42+**

Welcome to the **PC Automation** package! This module unlocks Hecos' physical superpowers, allowing it to take direct control of your computer's mouse, keyboard, and application windows. When combined with **Vision (Webcam / Desktop Screenshot)**, it transforms Hecos into a virtual operator that "sees" your screen and clicks exactly where needed, just like you would.

---

## 🌟 Practical Examples

Here is what you can ask Hecos in the chat to immediately test the power of this module:

### 1. Window Management (Without Vision)
Hecos can manage your background applications without needing to see the screen.
> *"What windows are currently open on my PC?"*  
> *"Minimize Google Chrome."*  
> *"Bring Spotify to the foreground."*

### 2. Vision Synergy (See and Click)
Hecos can take a screenshot to understand what's on the screen and move the mouse accordingly.
> *"Look at my screen: click on the 'Submit' button you see on the bottom right."*  
> *"Take a screenshot, find the recycle bin icon on the desktop, and double-click it."*

### 3. Typing and Keyboard Control
Hecos can type entire texts at superhuman speed or execute complex shortcut commands for you.
> *"Open Notepad (use the win key) and write a short summary of our conversation."*  
> *"Press Ctrl+C to copy the selected text, then open a new tab in the browser (Ctrl+T) and paste it (Ctrl+V)."*

### 4. Windows Accessibility (Windows Exclusive)
Hecos can read the system's accessibility tree to understand what you are looking at, without taking a screenshot!
> *"What tabs do I have open in my browser right now?"*  
> *"Switch to the 'YouTube' tab in my browser."*

---

## ⚡ Slash Commands

If you don't want to go through the AI, you can issue direct and instant orders using **Slash Commands**. Type them directly into the Hecos chat input:

| Command | Description | Example Usage |
|---|---|---|
| `/click_text <text>` | Takes an invisible screenshot, finds the word via OCR, and clicks it. Great for avoiding x,y coordinates! | `/click_text Submit` |
| `/type <text>` | Types text on the keyboard instantly. | `/type rm -rf /` |
| `/hotkey <keys>` | Executes a keyboard shortcut. | `/hotkey ctrl+shift+esc` |
| `/focus <title>` | Instantly brings a window to the foreground. | `/focus discord` |

> 💡 **Flows Note:** All these slash commands can be used inside the `Command` nodes of **Hecos Flows**! You can create advanced macros that open programs, click specific texts, and fill forms without consuming a single AI token.

---

## ⚠️ Safety and FailSafe

Giving control of your PC to an AI can be scary. Don't panic! 
This module includes a bulletproof **FailSafe** system (powered by *PyAutoGUI*). 
If Hecos is doing something you don't want or has "taken over", **violently move your physical mouse to the top-left corner of the screen**. This will instantly disable the automation engine and abort the action.

---

## 🛠️ System Requirements

- **Mouse / Keyboard / Windows:** Natively compatible with Windows, macOS, and Linux.
- **Browser Tab Interception (`/focus_browser_tab`):** Works only on Windows (requires `pywinauto`).
- **Text-based clicking (`/click_text`):** Requires **Tesseract OCR** installed on the system.
  - Windows: [Download from UB-Mannheim](https://github.com/UB-Mannheim/tesseract/wiki)
  - macOS: `brew install tesseract`
  - Linux: `sudo apt install tesseract-ocr`
