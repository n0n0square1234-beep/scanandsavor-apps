import json
import os

MEAL_PLANS_FILE = "meal_plans.json"

def load_meal_plans():
    if not os.path.exists(MEAL_PLANS_FILE):
        return []
    with open(MEAL_PLANS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_meal_plan(plan):
    plans = load_meal_plans()
    plans.append(plan)
    with open(MEAL_PLANS_FILE, "w", encoding="utf-8") as f:
        json.dump(plans, f, ensure_ascii=False, indent=2)
    return plans

def remove_meal_plan(index):
    plans = load_meal_plans()
    if 0 <= index < len(plans):
        plans.pop(index)
    with open(MEAL_PLANS_FILE, "w", encoding="utf-8") as f:
        json.dump(plans, f, ensure_ascii=False, indent=2)
    return plans