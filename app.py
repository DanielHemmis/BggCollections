from flask import Flask, render_template, request
from bgg_utils import fetch_user_collection, process_collection, format_collection_to_dataframe
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)


@app.route("/", methods=["GET", "POST"])
def index():
    combined_collection = {}
    usernames = []

    if request.method == "POST":
        usernames = request.form.get("usernames", "").split(",")
        usernames = [username.strip() for username in usernames if username.strip()]

        user_collections = []
        valid_usernames = []

        for username in usernames:
            user_data = fetch_user_collection(username)
            if user_data['collection']:
                user_collections.append(user_data['collection'])
                valid_usernames.append(username)
            else:
                print(f"Collection for {username} not found.")

        with ThreadPoolExecutor() as executor:
            futures = {executor.submit(process_collection, username, collection, combined_collection): username
                       for username, collection in zip(valid_usernames, user_collections)}
            for future in as_completed(futures):
                future.result()

        df = format_collection_to_dataframe(combined_collection)
        table_html = df.to_html(index=False, escape=False, table_id="gameTable")

    else:
        table_html = ""

    return render_template("index.html", table_html=table_html, usernames=", ".join(usernames))


if __name__ == "__main__":
    app.run(debug=True)
