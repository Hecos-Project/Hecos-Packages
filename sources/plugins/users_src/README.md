# Users Profile Tools

This package provides Artificial Intelligence tools (LLM Tools) to read and update user preferences and profile information (email, contacts, biography, preferred language).
It does not contain any user interface as this is managed directly by the Hecos Core (`System Config -> Users`).

**Included Tools:**
- `get_profile(username)`: Extracts data from the Authentication Database (Core).
- `update_profile(username, **kwargs)`: Saves profile updates on behalf of the user.
