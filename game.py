from boardgamegeek import BGGClient

# Initialize the BGG client
bgg = BGGClient()


def fetch_game_details(game_id):
    """Fetch game details by ID and return relevant information."""
    retries = 3  # Number of retries for fetching game details
    for attempt in range(retries):
        try:
            # Specify the game_id parameter correctly
            game_details = bgg.game(game_id=game_id)

            # Extract BGG Rank specifically for "Board Game Rank"
            bgg_rank = "N/A"
            for rank in game_details.stats.get("ranks", []):
                # Check for the "Board Game Rank"
                if rank.get("name") == "boardgame":
                    bgg_rank = rank.get("value", "N/A")
                    break  # Exit loop once we find the rank

            return {
                "name": game_details.name,  # Game name
                "bgg_rank": bgg_rank,  # BGG Rank
                "rating": game_details.rating_average,  # Average rating
                "weight": game_details.stats.get("averageweight", "N/A"),  # Average weight
                "min_players": game_details.min_players,  # Minimum players
                "max_players": game_details.max_players,  # Maximum players
                "playtime": game_details.playing_time  # Playing time
            }
        except Exception as e:
            print(f"Attempt {attempt + 1} failed for game ID {game_id}: {e}")
    print(f"Failed to fetch details for game ID {game_id} after {retries} attempts.")
    return None


# Replace with a valid game ID to test
test_game_id = 13  # Example game ID

game_info = fetch_game_details(test_game_id)
if game_info:
    print(f"Game Name: {game_info['name']}")
    print(f"BGG Rank: {game_info['bgg_rank']}")
    print(f"Average Rating: {game_info['rating']}")
    print(f"Average Weight: {game_info['weight']}")
    print(f"Players: {game_info['min_players']} - {game_info['max_players']}")
    print(f"Playtime: {game_info['playtime']} minutes")
else:
    print("Could not retrieve game information.")
