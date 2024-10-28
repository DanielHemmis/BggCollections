from boardgamegeek import BGGClient
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
from threading import Lock
import time

# Initialize the BGG client and thread-safe print lock
bgg = BGGClient()
print_lock = Lock()


# Retry mechanism for fetching collections
def fetch_with_retries(func, *args, max_retries=3, **kwargs):
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1)
            else:
                print(f"Failed to retrieve data after {max_retries} retries: {e}")
    return None


# Fetch collection for a user
def fetch_user_collection(username):
    user_collection_data = {'collection': [], 'errors': []}
    collection = fetch_with_retries(bgg.collection, username, wishlist=False)

    if collection is not None and len(collection) > 0:
        owned_games = [game for game in collection if hasattr(game, 'owned') and game.owned]
        user_collection_data['collection'] = owned_games
    else:
        user_collection_data['errors'].append(f"No collection found for {username}")

    return user_collection_data


# Process the collection
def process_collection(username, collection, combined_collection):
    expansions_to_attach = {}
    game_ids = [str(game.id) for game in collection]

    game_details_list = []
    for game_id_chunk in chunk_list(game_ids, 20):
        try:
            chunk_details = bgg.game_list(game_id_chunk)
            game_details_list.extend(chunk_details)
        except Exception as e:
            print(f"Failed to fetch game details for chunk: {e}")

    for game in collection:
        game_id = game.id
        game_details = next((g for g in game_details_list if g.id == game_id), None)

        if game_details:
            if game_details._expands:
                base_game_id = game_details._expands[0].id
                if base_game_id in combined_collection:
                    expansion_link = f'<a href="https://boardgamegeek.com/boardgame/{game_details.id}">{game_details.name}</a>'
                    if expansion_link not in combined_collection[base_game_id]["expansions"]:
                        combined_collection[base_game_id]["expansions"].append(expansion_link)
                    continue

            bgg_rank = 999999
            for rank in game_details.stats.get("ranks", []):
                if rank.get("name") == "boardgame":
                    rank_value = rank.get("value")
                    if rank_value not in (None, "N/A"):
                        bgg_rank = str(int(float(rank_value)))
                    break

            game_link = f'<a href="https://boardgamegeek.com/boardgame/{game_details.id}">{game_details.name}</a>'
            game_thumbnail = game_details.thumbnail if game_details.thumbnail else ''

            if game_id not in combined_collection:
                combined_collection[game_id] = {
                    "image": f'<img src="{game_thumbnail}">' if game_thumbnail else '',
                    "name": game_link,
                    "total_plays": game.numplays,
                    "bgg_rank": bgg_rank,
                    "rating": round(game_details.rating_average, 1) if game_details.rating_average else "-",
                    "weight": round(game_details.stats.get("averageweight", 1), 1) if game_details.stats.get("averageweight") else "-",
                    "min_players": game_details.min_players,
                    "max_players": game_details.max_players,
                    "playtime": game_details.playing_time,
                    "expansions": [],
                    "owners": username
                }

                if game_id in expansions_to_attach:
                    combined_collection[game_id]["expansions"].extend(expansions_to_attach[game_id])
                    del expansions_to_attach[game_id]

            else:
                combined_collection[game_id]["owners"] += f", {username}"
                combined_collection[game_id]["total_plays"] += game.numplays
        else:
            print(f"No details found for game ID: {game_id}")

    return combined_collection


# Helper to chunk list of game IDs
def chunk_list(lst, chunk_size):
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]


# Format and sort collection data, returning as a DataFrame
def format_collection_to_dataframe(combined_collection):
    for game in combined_collection.values():
        if isinstance(game["expansions"], list):
            game["expansions"] = ' | '.join(game["expansions"])

    sorted_collection = sorted(combined_collection.values(), key=lambda x: x['name'].split('>')[1].split('<')[0])
    df = pd.DataFrame(sorted_collection)
    df.rename(columns={
        "image": "Image", "name": "Game Name", "total_plays": "Total Plays", "bgg_rank": "BGG Rank",
        "rating": "Average Rating", "weight": "Average Weight", "min_players": "Min Players",
        "max_players": "Max Players", "playtime": "Playtime (min)", "expansions": "Expansions",
        "owners": "Owners"
    }, inplace=True)

    return df
