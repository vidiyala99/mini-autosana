"""The benchmark suite.

15 tasks across 3 public demo sites, ordered roughly easy → hard within each
site. Tasks are intentionally short and self-contained — a single trial should
average ~10 agent steps, keeping cost per trial under $0.05.

Each task carries a `success_check` — a yes/no visual question asked of the
final screenshot. This is our ground truth: the agent's own claim of success
is checked against an independent visual judge before we credit it.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Task:
    id: str
    site: str
    url: str
    goal: str
    success_check: str
    difficulty: str  # easy | medium | hard


SAUCEDEMO_URL = "https://www.saucedemo.com/"
TODOMVC_URL = "https://todomvc.com/examples/react/dist/"
WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/Main_Page"


TASKS: list[Task] = [
    # --- saucedemo.com ---------------------------------------------------
    Task(
        id="sauce_login",
        site="saucedemo",
        url=SAUCEDEMO_URL,
        goal="Log in with username 'standard_user' and password 'secret_sauce'.",
        success_check="Is the products inventory page visible with multiple product cards?",
        difficulty="easy",
    ),
    Task(
        id="sauce_add_cheapest",
        site="saucedemo",
        url=SAUCEDEMO_URL,
        goal=(
            "Log in with username 'standard_user' and password 'secret_sauce'. "
            "Sort products by price (low to high). Add the first (cheapest) product to the cart."
        ),
        success_check="Does the cart icon in the top-right show a badge with the number 1?",
        difficulty="medium",
    ),
    Task(
        id="sauce_sort_price_desc",
        site="saucedemo",
        url=SAUCEDEMO_URL,
        goal=(
            "Log in with username 'standard_user' and password 'secret_sauce'. "
            "Sort the products by price from high to low."
        ),
        success_check="Is the first product card showing the highest-priced item ('Sauce Labs Fleece Jacket' at $49.99)?",
        difficulty="medium",
    ),
    Task(
        id="sauce_checkout",
        site="saucedemo",
        url=SAUCEDEMO_URL,
        goal=(
            "Log in as standard_user / secret_sauce. Add 'Sauce Labs Backpack' to the cart, "
            "go to the cart, click Checkout, fill in first name 'Test', last name 'User', "
            "postal code '12345', click Continue, then click Finish."
        ),
        success_check="Is the 'Thank you for your order!' confirmation message visible?",
        difficulty="hard",
    ),
    Task(
        id="sauce_logout",
        site="saucedemo",
        url=SAUCEDEMO_URL,
        goal=(
            "Log in as standard_user / secret_sauce. Then open the hamburger menu "
            "(top-left) and click Logout."
        ),
        success_check="Is the login form with Username and Password fields visible?",
        difficulty="medium",
    ),
    # --- todomvc ---------------------------------------------------------
    Task(
        id="todo_add_one",
        site="todomvc",
        url=TODOMVC_URL,
        goal="Add a single todo item with the text 'buy milk' and press Enter.",
        success_check="Is there a todo item visible in the list with the text 'buy milk'?",
        difficulty="easy",
    ),
    Task(
        id="todo_complete_middle",
        site="todomvc",
        url=TODOMVC_URL,
        goal=(
            "Add three todos: 'apples', 'bread', 'cheese' (pressing Enter after each). "
            "Then mark the middle one ('bread') as completed by clicking its checkbox."
        ),
        success_check="Is the 'bread' todo shown with a strikethrough or checked state, while 'apples' and 'cheese' are not?",
        difficulty="hard",
    ),
    Task(
        id="todo_add_delete",
        site="todomvc",
        url=TODOMVC_URL,
        goal=(
            "Add a todo 'temporary item', then delete it by hovering over it and clicking the X button on the right."
        ),
        success_check="Is the todo list empty (no items shown)?",
        difficulty="medium",
    ),
    Task(
        id="todo_filter_active",
        site="todomvc",
        url=TODOMVC_URL,
        goal=(
            "Add two todos: 'task one' and 'task two'. Mark 'task one' as completed by clicking its checkbox. "
            "Then click the 'Active' filter at the bottom."
        ),
        success_check="Is only 'task two' visible in the list (the completed 'task one' is hidden)?",
        difficulty="hard",
    ),
    Task(
        id="todo_clear_completed",
        site="todomvc",
        url=TODOMVC_URL,
        goal=(
            "Add two todos: 'one' and 'two'. Mark both as completed by clicking each checkbox. "
            "Then click 'Clear completed' at the bottom."
        ),
        success_check="Is the todo list completely empty?",
        difficulty="hard",
    ),
    # --- wikipedia -------------------------------------------------------
    Task(
        id="wiki_search_einstein",
        site="wikipedia",
        url=WIKIPEDIA_URL,
        goal="Use the search box to search for 'Albert Einstein' and navigate to his article page.",
        success_check="Is the page heading 'Albert Einstein' visible at the top of the article?",
        difficulty="easy",
    ),
    Task(
        id="wiki_einstein_to_relativity",
        site="wikipedia",
        url=WIKIPEDIA_URL,
        goal=(
            "Search for 'Albert Einstein' and open his article. Then click a link in the article "
            "that goes to the 'Theory of relativity' page."
        ),
        success_check="Is the page heading showing 'Theory of relativity' or similar?",
        difficulty="hard",
    ),
    Task(
        id="wiki_random",
        site="wikipedia",
        url=WIKIPEDIA_URL,
        goal="Click the 'Random article' link in the left sidebar.",
        success_check="Has the page navigated away from the Main Page to a different Wikipedia article?",
        difficulty="easy",
    ),
    Task(
        id="wiki_search_python",
        site="wikipedia",
        url=WIKIPEDIA_URL,
        goal=(
            "Search for 'Python (programming language)' and open that exact article."
        ),
        success_check="Is the page heading 'Python (programming language)' visible at the top?",
        difficulty="medium",
    ),
    Task(
        id="wiki_today_featured",
        site="wikipedia",
        url=WIKIPEDIA_URL,
        goal=(
            "On the Main Page, find the 'From today's featured article' section and click its 'Full article' or main title link "
            "to open the featured article."
        ),
        success_check="Has the page navigated to a Wikipedia article page (not the Main Page)?",
        difficulty="hard",
    ),
]


TASKS_BY_ID = {t.id: t for t in TASKS}
