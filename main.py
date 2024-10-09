from boardgamegeek import BGGClient
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import webbrowser
import os
from threading import Lock

# Initialize the BGG client
bgg = BGGClient()

# List of BGG usernames to fetch collections for
usernames = ["AtomikVoid", "Krizszs"]

# Dictionary to hold combined collection data
combined_collection = {}

# Lock for thread-safe printing
print_lock = Lock()


# Function to chunk the game IDs
def chunk_list(lst, chunk_size):
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]


# Function to fetch collection for a user
def fetch_user_collection(username):
    user_collection_data = {
        'collection': [],
        'errors': []
    }

    try:
        # Fetch user's collection
        collection = bgg.collection(username, wishlist=False)
        user_collection_data['collection'] = collection
    except Exception as e:
        user_collection_data['errors'].append(f"Failed to fetch collection for {username}: {e}")

    return user_collection_data


# Function to process the fetched collection
def process_collection(username, collection):
    global combined_collection
    total_games = len(collection)  # Track total games for this user
    games_fetched = 0  # Track number of games fetched

    # Collect game IDs for batch fetching
    game_ids = [str(game.id) for game in collection]  # Ensure game IDs are strings
    print(f"Fetching game details for {username} - Total games: {total_games}")

    # Store the initial progress message
    progress_message = f"Fetching {username}: 0 / {total_games} games fetched."

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
        # Find game details for the current game ID
        game_details = next((g for g in game_details_list if g.id == game_id), None)

        if game_details:
            bgg_rank = "-"
            # Extract BGG rank
            for rank in game_details.stats.get("ranks", []):
                if rank.get("name") == "boardgame":
                    rank_value = rank.get("value")  # Get the rank value
                    if rank_value not in (None, "N/A"):  # Check for valid value
                        bgg_rank = str(int(float(rank_value)))  # Convert to float first to handle any decimals, then to int, then to str
                    break

            # Check if game is already in the combined collection
            if game_id not in combined_collection:
                # Initialize the game entry
                combined_collection[game_id] = {
                    "name": game.name,
                    "total_plays": game.numplays,
                    "bgg_rank": bgg_rank,
                    "rating": round(game_details.rating_average, 1) if game_details.rating_average is not None else "-",  # Round to 1 decimal
                    "weight": round(game_details.stats.get("averageweight", 0), 1) if game_details.stats.get("averageweight") is not None else "-",  # Round to 1 decimal
                    "min_players": game_details.min_players,
                    "max_players": game_details.max_players,
                    "playtime": game_details.playing_time,
                    "owners": username  # Store as a string
                }
            else:
                # If game is already there, append the current username to the Owners string
                combined_collection[game_id]["owners"] += f", {username}"  # Append to the existing string
                combined_collection[game_id]["total_plays"] += game.numplays


# Main function to fetch and process user collections using threads
def main():
    # First, fetch collections to get the total game count
    user_collections = []
    total_games = 0  # Total number of games across all users

    for username in usernames:
        user_data = fetch_user_collection(username)
        if user_data['collection']:
            user_collections.append(user_data['collection'])
            total_games += len(user_data['collection'])  # Accumulate the total games for all users

    # Now process each user's collection
    with ThreadPoolExecutor() as executor:
        futures = {executor.submit(process_collection, username, collection): username for username, collection in zip(usernames, user_collections)}

        for future in as_completed(futures):
            username = futures[future]
            try:
                future.result()  # No additional processing needed here
            except Exception as e:
                with print_lock:
                    print(f"\nAn error occurred while processing data for {username}: {e}")

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

    # Adding custom styling and DataTables integration
    styled_html = f"""
        <html>
            <head>
                <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/1.13.1/css/jquery.dataTables.css">
                <script type="text/javascript" charset="utf8" src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
                <script type="text/javascript" charset="utf8" src="https://cdn.datatables.net/1.13.1/js/jquery.dataTables.min.js"></script>
                <script type="text/javascript">
                    $(document).ready(function() {{
                        $('#gameTable').DataTable();
                    }});
                </script>
                <style>
                    table {{
                        width: 100%;
                        border-collapse: collapse;
                    }}
                    th, td {{
                        text-align: left;
                        padding: 8px;
                        border: 1px solid #ddd;
                    }}
                    th {{
                        background-color: #f2f2f2;
                    }}
                </style>
            </head>
            <body>
                {html.replace('<table', '<table id="gameTable"')}
            </body>
        </html>
        """

    with open(output_file, "w") as f:
        f.write(styled_html)

    print(f"Output written to {os.path.realpath(output_file)}")

    # Open the HTML file in the default web browser
    webbrowser.open('file://' + os.path.realpath(output_file))


if __name__ == "__main__":
    main()
