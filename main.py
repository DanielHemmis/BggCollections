import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import webbrowser
import os
from threading import Lock
import time
import xml.etree.ElementTree as ET

# List of BGG usernames to fetch collections for
usernames = ["AtomikVoid", "Krizszs"]

# Dictionary to hold combined collection data
combined_collection = {}

# Lock for thread-safe printing
print_lock = Lock()


# Function to fetch data from BGG XML API
def fetch_from_bgg(endpoint, params=None):
    base_url = "https://boardgamegeek.com/xmlapi2/"
    print(f"Fetching from URL: {base_url + endpoint} with params: {params}")  # Debug URL and parameters
    response = requests.get(base_url + endpoint, params=params)

    try:
        response.raise_for_status()  # Raise an error for bad responses
        print(f"Successfully fetched data from {base_url + endpoint}")  # Successful fetch
    except requests.exceptions.HTTPError as e:
        print(f"HTTP error occurred: {e} - Response content: {response.content}")  # Log HTTP errors
        raise
    except Exception as e:
        print(f"An error occurred: {e}")  # Log general errors

    return response.content  # Return the raw content for further inspection


# Function to retry fetching collections
def fetch_with_retries(func, *args, max_retries=3, **kwargs):
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"Error fetching data for {args}, retrying ({attempt + 1}/{max_retries})")
                time.sleep(1)  # Wait before retrying
            else:
                print(f"Failed to retrieve data after {max_retries} retries: {e}")
    return None


# Function to fetch collection for a user
def fetch_user_collection(username):
    user_collection_data = {
        'collection': [],
        'errors': []
    }

    # Fetch the collection XML data
    collection_xml = fetch_with_retries(fetch_from_bgg, 'collection', {'username': username, 'wishlist': '0'})

    # Parse the collection XML
    if collection_xml is not None:
        try:
            # Print the raw XML response for debugging
            print(f"Raw XML response for {username}:\n{collection_xml.decode('utf-8')}")  # Decode bytes to string

            # Parse the XML
            root = ET.fromstring(collection_xml)
            for item in root.findall('item'):
                game_id = item.get('objectid')
                user_collection_data['collection'].append(game_id)

            print(f"Collection for {username} fetched: {len(user_collection_data['collection'])} games")
        except ET.ParseError as e:
            user_collection_data['errors'].append(f"XML parse error for {username}: {e}")
            print(f"Failed to parse XML for {username}: {e}")
        except Exception as e:
            user_collection_data['errors'].append(f"Error processing collection for {username}: {e}")
            print(f"Error processing collection for {username}: {e}")
    else:
        user_collection_data['errors'].append(f"No collection found for {username}")

    return user_collection_data


def process_collection(username, collection):
    global combined_collection
    expansions_to_attach = {}  # Temporary storage for expansions waiting for base games
    total_games = len(collection)  # Track total games for this user
    games_fetched = 0  # Track number of games fetched

    # Fetch details for game IDs in chunks
    game_details_list = []
    for game_id_chunk in chunk_list(collection, 20):  # Process in chunks of 20
        try:
            print(f"Fetching details for chunk: {game_id_chunk}")  # Debug chunk being fetched
            game_details_xml = fetch_with_retries(fetch_from_bgg, 'thing', {'id': ",".join(game_id_chunk)})
            for game in game_details_xml.findall('item'):
                game_id = game.get('id')
                game_details_list.append(game)

                # Update game count after fetching each game in the chunk
                games_fetched += 1

                # Update the progress message in a thread-safe way
                with print_lock:
                    progress_message = f"Fetching {username}: {games_fetched} / {total_games} games fetched"
                    print(f"\r{progress_message}", end='', flush=True)  # Update this user's progress

        except Exception as e:
            with print_lock:
                print(f"\nFailed to fetch game details for chunk: {e}")

    # Process each game in the collection
    for game_id in collection:
        game_details = next((g for g in game_details_list if g.get('id') == game_id), None)

        if game_details:
            # Check if the game is an expansion of another game
            expands = game_details.find('expands')
            if expands is not None:
                base_game_id = expands.get('id')
                if base_game_id in combined_collection:
                    # Add this expansion to the base game's entry immediately
                    expansion_link = f'<a href="https://boardgamegeek.com/boardgame/{game_details.get("id")}">{game_details.find("name").text}</a>'
                    # Only append if the expansion is not already in the list
                    if expansion_link not in combined_collection[base_game_id]["expansions"]:
                        combined_collection[base_game_id]["expansions"].append(expansion_link)
                        with print_lock:
                            print(f"\nAdded expansion: {game_details.find('name').text} to base game: {base_game_id}")
                    continue  # Skip processing this as a base game

            bgg_rank = "-"
            try:
                # Extract BGG rank
                ranks = game_details.find('statistics/ranks')
                if ranks is not None:
                    for rank in ranks.findall('rank'):
                        if rank.get('name') == "boardgame":
                            rank_value = rank.get('value')
                            if rank_value not in (None, "N/A"):
                                bgg_rank = str(int(float(rank_value)))  # Convert to string after removing decimals
                            break

                # Create the base game link
                game_link = f'<a href="https://boardgamegeek.com/boardgame/{game_details.get("id")}">{game_details.find("name").text}</a>'

                # Check if the base game is already in the combined collection
                if game_id not in combined_collection:
                    # Initialize the base game entry
                    combined_collection[game_id] = {
                        "name": game_link,
                        "total_plays": 0,  # Placeholder for plays
                        "bgg_rank": bgg_rank,
                        "rating": round(float(game_details.find("rating/average").text), 1) if game_details.find(
                            "rating/average") is not None else "-",
                        "weight": round(float(game_details.find("statistics/averageweight").text),
                                        1) if game_details.find("statistics/averageweight") is not None else "-",
                        "min_players": int(game_details.find("minplayers").text),
                        "max_players": int(game_details.find("maxplayers").text),
                        "playtime": int(game_details.find("playingtime").text),
                        "expansions": [],
                        "owners": username
                    }

                with print_lock:
                    print(f"\nProcessed game: {game_details.find('name').text} (ID: {game_id})")

            except Exception as e:
                with print_lock:
                    print(f"\nError processing game details for {game_details.find('name').text}: {e}")

        else:
            with print_lock:
                print(f"\nNo details found for game ID: {game_id}")

    # Debug output for combined collection after processing
    with print_lock:
        if not combined_collection:
            print(f"\nCombined collection is empty after processing {username}.")
        else:
            print(f"\nCombined collection after processing {username}: {len(combined_collection)}")


# Function to chunk the game IDs
def chunk_list(lst, chunk_size):
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]


# Main function to fetch and process user collections using threads
def main():
    user_collections = []
    valid_usernames = []  # List to store usernames with valid collections
    total_games = 0  # Total number of games across all users

    print(f"Fetching collections for users: {usernames}")

    # Fetch collections for each user
    for username in usernames:
        user_data = fetch_user_collection(username)
        if user_data['collection']:
            user_collections.append(user_data['collection'])
            valid_usernames.append(username)  # Add valid username
            total_games += len(user_data['collection'])  # Accumulate the total games for all users
        else:
            print(f"Collection for {username} not found.")
            if user_data['errors']:
                for error in user_data['errors']:
                    print(f"Error: {error}")

    # Only process if there are valid user collections
    if not valid_usernames:
        print("No valid user collections found. Exiting.")
        return

    # Use threading to fetch game details concurrently
    with ThreadPoolExecutor() as executor:
        futures = {executor.submit(process_collection, username, user_collections[i]): username for i, username in
                   enumerate(valid_usernames)}

        for future in as_completed(futures):
            username = futures[future]
            try:
                future.result()  # Ensure any exceptions are raised
            except Exception as e:
                with print_lock:
                    print(f"Error processing collection for {username}: {e}")

    # Check combined collection for contents
    if not combined_collection:
        print("Combined collection is empty. No games were processed.")
        return

    # Sort the combined collection by game name
    sorted_collection = sorted(combined_collection.values(), key=lambda x: x['name'])

    # Create a DataFrame for further processing or export
    df = pd.DataFrame(sorted_collection)

    # Rename columns to be more user-friendly
    df.rename(columns={
        "name": "Game Name",
        "total_plays": "Total Plays",
        "bgg_rank": "BGG Rank",
        "rating": "Average Rating",
        "weight": "Average Weight",
        "min_players": "Min Players",
        "max_players": "Max Players",
        "playtime": "Playtime (min)",
        "expansions": "Expansions",
        "owners": "Owners"
    }, inplace=True)

    # Output the DataFrame to an HTML file with left-aligned text
    output_file = "combined_board_game_collection.html"
    html = df.to_html(index=False, escape=False)

    # Adding custom styling for the table
    styled_html = f"""
        <html>
            <head>
                <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/1.13.1/css/jquery.dataTables.css">
                <script type="text/javascript" charset="utf-8" src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
                <script type="text/javascript" charset="utf-8" src="https://cdn.datatables.net/1.13.1/js/jquery.dataTables.min.js"></script>
                <script type="text/javascript">
                    $(document).ready(function() {{
                        $('#gameTable').DataTable({{
                            "order": [[0, "asc"]],
                            "columnDefs": [{{
                                "targets": [9], // Assuming 'Owners' is the last column (index 9)
                                "visible": true,
                                "searchable": false
                            }}]
                        }});
                    }});
                </script>
                <style>
                    table {{
                        width: 100%;
                        border-collapse: collapse;
                        text-align: left;
                    }}
                    th, td {{
                        padding: 8px;
                        border: 1px solid #ddd;
                    }}
                    th {{
                        background-color: #f2f2f2;
                    }}
                </style>
            </head>
            <body>
                <h2>Headline</h2>
                {html.replace('<table', '<table id="gameTable"')}
            </body>
        </html>
    """

    # Write the styled HTML to a file
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(styled_html)

    # Open the output file in the web browser
    webbrowser.open('file://' + os.path.realpath(output_file))


if __name__ == "__main__":
    main()