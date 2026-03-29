import os
import base64
from anthropic import Anthropic
from dotenv import load_dotenv
 
load_dotenv()
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
 
def analyze_image(image_data, media_type):
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": image_data
                    }
                },
                {
                    "type": "text",
                    "text": "Look at this photo of a fridge or pantry. List every food ingredient you can see. Return ONLY a comma separated list of ingredients, nothing else. Example: chicken, milk, eggs, garlic, pasta"
                }
            ]
        }]
    )
    ingredients_text = message.content[0].text
    ingredients = [i.strip() for i in ingredients_text.split(',') if i.strip()]
    return ingredients
 
meal_keywords = {
    "breakfast": ["egg", "bacon", "oat", "milk", "bread", "butter", "banana", "berry", "yogurt", "cheese", "ham", "syrup", "honey", "fruit", "orange", "apple", "cream", "flour", "sugar"],
    "lunch": ["chicken", "turkey", "tuna", "bread", "lettuce", "tomato", "cheese", "avocado", "bean", "rice", "pasta", "lemon", "olive", "onion", "pepper", "cucumber", "carrot", "celery"],
    "dinner": ["chicken", "beef", "pork", "fish", "salmon", "shrimp", "pasta", "rice", "potato", "onion", "garlic", "tomato", "pepper", "broccoli", "carrot", "zucchini", "mushroom", "butter", "cream"],
    "dessert": ["sugar", "flour", "butter", "egg", "milk", "cream", "chocolate", "vanilla", "honey", "apple", "banana", "berry", "lemon", "orange", "cinnamon", "nutmeg", "cocoa", "caramel", "coconut", "almond", "maple", "pear", "peach", "mango", "oat", "brown sugar", "powdered sugar", "baking soda", "baking powder", "strawberr", "blueberr", "raspberry", "cherry"]
}
 
meal_defaults = {
    "breakfast": ["eggs", "butter", "flour", "milk", "sugar"],
    "lunch": ["bread", "chicken", "lettuce", "tomato", "cheese"],
    "dinner": ["chicken", "garlic", "olive oil", "pasta", "onion"],
    "dessert": ["butter", "sugar", "flour", "eggs", "vanilla"]
}
 
def filter_by_meal(ingredients, meal_type):
    if not meal_type:
        return ingredients
    keywords = meal_keywords.get(meal_type, [])
    filtered = [ing for ing in ingredients if any(kw in ing.lower() for kw in keywords)]
    if len(filtered) < 3:
        defaults = meal_defaults.get(meal_type, [])
        for d in defaults:
            if d not in filtered:
                filtered.append(d)
    return filtered
 
def generate_recipe_list(ingredients, dietary_restrictions=[], meal_type="", cook_time=""):
    if meal_type:
        ingredients = filter_by_meal(ingredients, meal_type)
 
    ingredient_list = ", ".join(ingredients)
    diet_list = ", ".join(dietary_restrictions)
    diet_text = "Dietary requirements: " + diet_list + "." if diet_list else ""
    time_text = "Each recipe MUST be completable in " + cook_time + " or less." if cook_time else ""
 
    meal_examples = {
        "breakfast": "pancakes, omelette, french toast, smoothie bowl, breakfast burrito",
        "lunch": "sandwich, salad, soup, wrap, grain bowl",
        "dinner": "pasta, stir fry, roasted chicken, tacos, curry",
        "dessert": "apple crisp, cinnamon cake, fruit pie, cookies, pudding, brownies, fried apples"
    }
 
    if meal_type:
        examples = meal_examples.get(meal_type, "")
        system_prompt = "You are a pastry chef who ONLY makes " + meal_type + " recipes such as " + examples + ". You are forbidden from making any savory dish. Every recipe you create fits the " + meal_type + " category."
    else:
        system_prompt = "You are a professional chef and nutritionist who creates recipes based on available ingredients."
 
    user_prompt = "Give me 4 different " + (meal_type if meal_type else "general") + " recipe ideas using these ingredients: " + ingredient_list + "\n"
    user_prompt += diet_text + "\n" + time_text + "\n"
    user_prompt += "For each recipe give a name, one sentence description, and estimated nutrition per serving.\n"
    user_prompt += "Format exactly like this, with nothing else:\n"
    user_prompt += "1. RECIPE NAME: [name] | DESCRIPTION: [one sentence] | CALORIES: [number] | PROTEIN: [number] | CARBS: [number] | FAT: [number]\n"
    user_prompt += "2. RECIPE NAME: [name] | DESCRIPTION: [one sentence] | CALORIES: [number] | PROTEIN: [number] | CARBS: [number] | FAT: [number]\n"
    user_prompt += "3. RECIPE NAME: [name] | DESCRIPTION: [one sentence] | CALORIES: [number] | PROTEIN: [number] | CARBS: [number] | FAT: [number]\n"
    user_prompt += "4. RECIPE NAME: [name] | DESCRIPTION: [one sentence] | CALORIES: [number] | PROTEIN: [number] | CARBS: [number] | FAT: [number]"
 
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}]
    )
    return message.content[0].text
 
def generate_recipe(ingredients, dietary_restrictions=[], meal_type="", recipe_name="", cook_time=""):
    if meal_type:
        ingredients = filter_by_meal(ingredients, meal_type)
 
    ingredient_list = ", ".join(ingredients)
    diet_list = ", ".join(dietary_restrictions)
    diet_text = "Dietary requirements: " + diet_list + "." if diet_list else ""
    time_text = "This recipe MUST be completable in " + cook_time + " or less." if cook_time else ""
 
    meal_examples = {
        "breakfast": "pancakes, omelette, french toast, smoothie bowl, breakfast burrito",
        "lunch": "sandwich, salad, soup, wrap, grain bowl",
        "dinner": "pasta, stir fry, roasted chicken, tacos, curry",
        "dessert": "apple crisp, cinnamon cake, fruit pie, cookies, pudding, brownies, fried apples"
    }
 
    if meal_type:
        examples = meal_examples.get(meal_type, "")
        system_prompt = "You are a pastry chef and nutritionist who ONLY makes " + meal_type + " recipes such as " + examples + ". You are forbidden from making any savory dish. Every recipe you create is sweet and fits the " + meal_type + " category."
        user_prompt = "Make a " + meal_type + " recipe"
        if recipe_name:
            user_prompt += " called " + recipe_name
        user_prompt += " like " + examples + ".\n"
        user_prompt += "You MUST ONLY use these approved " + meal_type + " ingredients: " + ingredient_list + "\n"
        user_prompt += "Do NOT add any vegetables, meat, or savory ingredients.\n"
        user_prompt += diet_text + "\n" + time_text + "\n"
    else:
        system_prompt = "You are a professional chef and nutritionist."
        user_prompt = "Create a recipe"
        if recipe_name:
            user_prompt += " called " + recipe_name
        user_prompt += " using: " + ingredient_list + "\n"
        user_prompt += diet_text + "\n" + time_text + "\n"
 
    user_prompt += "Format exactly like this:\n"
    user_prompt += "RECIPE NAME: [name]\nTIME: [total time]\nSERVINGS: [number]\n"
    user_prompt += "CALORIES: [number only]\nPROTEIN: [number only in grams]\nCARBS: [number only in grams]\n"
    user_prompt += "FAT: [number only in grams]\nFIBER: [number only in grams]\nSUGAR: [number only in grams]\n"
    user_prompt += "SODIUM: [number only in mg]\nVITAMIN_C: [number only in mg]\nCALCIUM: [number only in mg]\n"
    user_prompt += "IRON: [number only in mg]\n"
    user_prompt += "INGREDIENTS:\n- [ingredient and amount]\n"
    user_prompt += "INSTRUCTIONS:\n1. [step]\n"
    user_prompt += "CHEF TIP: [one helpful tip]"
 
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1536,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}]
    )
    return message.content[0].text
 
def generate_meal_plan(ingredients, dietary_restrictions=[], days=7, budget=None, selected_meals=None):
    # Default to all three meals if none specified
    if selected_meals is None:
        selected_meals = ['breakfast', 'lunch', 'dinner']
 
    # Separate standard meals (AI generates options) from custom meals (user fills in)
    standard_meals = ['breakfast', 'lunch', 'dinner']
    ai_meals = [m for m in selected_meals if m in standard_meals]
 
    ingredient_list = ", ".join(ingredients) if ingredients else "common pantry staples"
    diet_list = ", ".join(dietary_restrictions)
    diet_text = "All meals must be: " + diet_list + "." if diet_list else ""
    budget_text = "The TOTAL estimated grocery cost for the entire meal plan must stay within $" + str(budget) + " based on average US grocery prices." if budget else ""
 
    # Build human-readable meal list for the prompt
    meals_str = ", ".join(m.upper() for m in ai_meals) if ai_meals else "LUNCH, DINNER"
 
    system_prompt = "You are a professional nutritionist and meal planner. You create balanced, varied weekly meal plans that are practical and delicious. When a budget is given, you select affordable ingredients and meals to stay within that budget based on average US supermarket prices. Be concise with meal names — keep them short."
 
    user_prompt = "Create a " + str(days) + " day meal plan.\n"
    user_prompt += "Available ingredients: " + ingredient_list + "\n"
    user_prompt += diet_text + "\n"
    user_prompt += budget_text + "\n"
    user_prompt += "Only include these meals each day: " + meals_str + "\n"
    user_prompt += "For each meal slot provide 3 different options. Keep meal names SHORT (max 5 words).\n"
    user_prompt += "At the very end after all days, add: ESTIMATED_TOTAL: $[number]\n"
    user_prompt += "Format EXACTLY like this for each day:\n\n"
 
    # Build format template based only on selected standard meals
    meal_keys = {
        'breakfast': ('BREAKFAST_1', 'BREAKFAST_2', 'BREAKFAST_3'),
        'lunch':     ('LUNCH_1',     'LUNCH_2',     'LUNCH_3'),
        'dinner':    ('DINNER_1',    'DINNER_2',    'DINNER_3'),
    }
 
    for i in range(1, days + 1):
        user_prompt += "DAY " + str(i) + ":\n"
        for meal in ai_meals:
            keys = meal_keys.get(meal, ())
            for key in keys:
                user_prompt += key + ": [name] | CALORIES: [n] | PROTEIN: [n]g | CARBS: [n]g | FAT: [n]g\n"
        user_prompt += "\n"
 
    user_prompt += "ESTIMATED_TOTAL: $[total cost]\n"
 
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=3500,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}]
    )
    return message.content[0].text
 
def generate_grocery_list(selected_meals, dietary_restrictions=[]):
    meal_list = ", ".join(selected_meals)
    diet_list = ", ".join(dietary_restrictions)
    diet_text = "All items must be suitable for: " + diet_list + "." if diet_list else ""
 
    system_prompt = "You are a professional chef and nutritionist who creates organized grocery lists with estimated prices based on average US supermarket prices in 2024."
 
    user_prompt = "Create a complete grocery list with estimated prices for these meals: " + meal_list + "\n"
    user_prompt += diet_text + "\n"
    user_prompt += "Organize by category. Include quantities and estimated price for each item based on average US grocery store prices.\n"
    user_prompt += "At the end add a GROCERY_TOTAL: $[number] line.\n"
    user_prompt += "Format exactly like this:\n\n"
    user_prompt += "PRODUCE:\n- [item and quantity] | $[price]\n\n"
    user_prompt += "MEAT & SEAFOOD:\n- [item and quantity] | $[price]\n\n"
    user_prompt += "DAIRY & EGGS:\n- [item and quantity] | $[price]\n\n"
    user_prompt += "PANTRY & DRY GOODS:\n- [item and quantity] | $[price]\n\n"
    user_prompt += "SPICES & SEASONINGS:\n- [item and quantity] | $[price]\n\n"
    user_prompt += "OTHER:\n- [item and quantity] | $[price]\n\n"
    user_prompt += "GROCERY_TOTAL: $[total]"
 
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}]
    )
    return message.content[0].text
 