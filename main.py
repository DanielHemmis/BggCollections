from boardgamegeek import BGGClient
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import webbrowser
import os
from threading import Lock
import time

# Initialize the BGG client
bgg = BGGClient()

# List of BGG usernames to fetch collections for
usernames = ["AtomikVoid", "Krizszs"]

# Dictionary to hold combined collection data
combined_collection = {}

# Lock for thread-safe printing
print_lock = Lock()


# Function to retry fetching collections
def fetch_with_retries(func, *args, max_retries=3, **kwargs):
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"Error fetching data, retrying... ({attempt + 1}/{max_retries})")
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

    collection = fetch_with_retries(bgg.collection, username, wishlist=False)
    if collection is not None:
        user_collection_data['collection'] = collection
        print(f"Collection for {username} fetched")
    else:
        user_collection_data['errors'].append(f"No collection found for {username}")

    return user_collection_data


def process_collection(username, collection):
    global combined_collection
    expansions_to_attach = {}  # Temporary storage for expansions waiting for base games
    total_games = len(collection)  # Track total games for this user
    games_fetched = 0  # Track number of games fetched

    # Collect game IDs for batch fetching
    game_ids = [str(game.id) for game in collection]  # Ensure game IDs are strings
    print(f"Fetching game details for {username} - Total games: {total_games}")

    # Fetch details for game IDs in chunks
    game_details_list = []
    for game_id_chunk in chunk_list(game_ids, 20):
        try:
            chunk_details = bgg.game_list(game_id_chunk)  # Fetch game details for the current chunk
            game_details_list.extend(chunk_details)  # Extend the list with results

            # Update game count after fetching each game in the chunk
            for game in chunk_details:
                games_fetched += 1  # Increment the fetched game count

                # Update the progress message in a thread-safe way
                with print_lock:
                    progress_message = f"Fetching {username}: {games_fetched} / {total_games} games fetched."
                    print(f"\r{progress_message}", end='', flush=True)  # Update this user's progress

        except Exception as e:
            with print_lock:
                print(f"\nFailed to fetch game details for chunk: {e}")

    # Process each game in the collection
    for game in collection:
        game_id = game.id
        game_details = next((g for g in game_details_list if g.id == game_id), None)

        if game_details:
            print(f"\nProcessing game: {game_details.name} (ID: {game_details.id})")  # Debug output

            # Check if the game is an expansion of another game
            if game_details._expands:
                base_game = game_details._expands[0]  # Assuming it expands one base game
                base_game_id = base_game.id

                if base_game_id in combined_collection:
                    # Add this expansion to the base game's entry immediately
                    combined_collection[base_game_id]["expansions"].append(game_details.name)
                    with print_lock:
                        print(f"\nAdded expansion: {game_details.name} to base game: {base_game.name}")
                else:
                    # Store the expansion to attach later if/when the base game is added
                    if base_game_id not in expansions_to_attach:
                        expansions_to_attach[base_game_id] = []
                    expansions_to_attach[base_game_id].append(game_details.name)
                    with print_lock:
                        print(f"\nStored expansion: {game_details.name} to attach to base game: {base_game.name}")
                continue  # Skip processing this as a base game

            # Process it as a base game
            print(f"\nAdding Base game: {game_details.name}")  # Debug output

            bgg_rank = "-"
            try:
                # Extract BGG rank
                for rank in game_details.stats.get("ranks", []):
                    if rank.get("name") == "boardgame":
                        rank_value = rank.get("value")
                        if rank_value not in (None, "N/A"):
                            bgg_rank = str(int(float(rank_value)))  # Convert to string after removing decimals
                        break

                # Check if the base game is already in the combined collection
                if game_id not in combined_collection:
                    # Initialize the base game entry
                    combined_collection[game_id] = {
                        "name": game.name,
                        "total_plays": game.numplays,
                        "bgg_rank": bgg_rank,
                        "rating": round(game_details.rating_average, 1) if game_details.rating_average is not None else "-",
                        "weight": round(game_details.stats.get("averageweight", 1), 1) if game_details.stats.get("averageweight") is not None else "-",
                        "min_players": game_details.min_players,
                        "max_players": game_details.max_players,
                        "playtime": game_details.playing_time,
                        "owners": username,
                        "expansions": []  # Initialize expansions list
                    }

                    with print_lock:
                        print(f"\nAdded base game: {game.name} to combined collection.")  # Debug message

                    # Attach any previously stored expansions for this base game
                    if game_id in expansions_to_attach:
                        combined_collection[game_id]["expansions"].extend(expansions_to_attach[game_id])
                        with print_lock:
                            print(f"\nAttached expansions: {expansions_to_attach[game_id]} to base game: {game.name}")
                        del expansions_to_attach[game_id]  # Remove after attaching

                else:
                    # If game is already there, append the current username to the Owners string
                    combined_collection[game_id]["owners"] += f", {username}"  # Append to the existing string
                    combined_collection[game_id]["total_plays"] += game.numplays

                # Debug message for successfully processed game
                with print_lock:
                    print(f"\nProcessed game: {game.name} - ID: {game_id}")

            except Exception as e:
                with print_lock:
                    print(f"\nError processing game details for {game.name}: {e}")

        else:
            with print_lock:
                print(f"\nNo details found for game ID: {game_id}")

    # Debug output for combined collection after processing
    with print_lock:
        if not combined_collection:
            print(f"\nCombined collection is empty after processing {username}.")
        else:
            print(f"\nCombined collection after processing {username}: {len(combined_collection)} games added.")


# Function to chunk the game IDs
def chunk_list(lst, chunk_size):
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]


# Main function to fetch and process user collections using threads
def main():
    user_collections = []
    total_games = 0  # Total number of games across all users

    print("Fetching collections for users:")

    # Fetch collections for each user
    for username in usernames:
        user_data = fetch_user_collection(username)
        if user_data['collection']:
            user_collections.append(user_data['collection'])
            total_games += len(user_data['collection'])  # Accumulate the total games for all users
        else:
            print(f"Collection for {username} not found.")

    # Now process each user's collection
    with ThreadPoolExecutor() as executor:
        futures = {executor.submit(process_collection, username, collection): username for username, collection in
                   zip(usernames, user_collections)}

        for future in as_completed(futures):
            username = futures[future]
            try:
                future.result()  # No additional processing needed here
            except Exception as e:
                with print_lock:
                    print(f"\nAn error occurred while processing data for {username}: {e}")

    # Check combined collection for contents
    if not combined_collection:
        print("Combined collection is empty. No games were processed.")
        return

    # Sort the combined collection by game name
    sorted_collection = sorted(combined_collection.values(), key=lambda x: x['name'])

    # Create a DataFrame from the sorted collection
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
                                "targets": [8], // Assuming 'Owners' is the last column (index 8)
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
                <h2>Combined Board Game Collection</h2>
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
