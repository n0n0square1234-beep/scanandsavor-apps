import json
import os

FAVORITES_FILE = "favorites.json"

def load_favorites():
    if not os.path.exists(FAVORITES_FILE):
        return []
    with open(FAVORITES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_favorite(recipe):
    favorites = load_favorites()
    favorites.append(recipe)
    with open(FAVORITES_FILE, "w", encoding="utf-8") as f:
        json.dump(favorites, f, ensure_ascii=False, indent=2)
    return favorites

def remove_favorite(index):
    favorites = load_favorites()
    if 0 <= index < len(favorites):
        favorites.pop(index)
    with open(FAVORITES_FILE, "w", encoding="utf-8") as f:
        json.dump(favorites, f, ensure_ascii=False, indent=2)
    return favorites