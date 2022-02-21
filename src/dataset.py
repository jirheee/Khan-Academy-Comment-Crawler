from glob import glob
import json
import util
import pandas as pd
import re

def load_comment_list():
    comment_jsons = glob("./data/comments/*/*/*.json")

    topics = []
    comment_dataset = []

    for i, comment_json in enumerate(comment_jsons):
        topic = re.findall('/[a-z0-9|-]+', comment_json)[2][1:]
        print(f"{i}/{len(comment_jsons)}: {topic}")
        with open(comment_json) as f:
            content_dict = json.loads("".join([l.strip() for l in f.readlines()]))
            for content in content_dict["articles"]:
                comment_dataset.extend(content["comments"])
                topics.extend([topic for _ in range(len(content["comments"]))])

            for content in content_dict["videos"]:
                comment_dataset.extend(content["comments"])
                topics.extend([topic for _ in range(len(content["comments"]))])

    print(f"Loaded {len(comment_dataset)} Comments")
    print(set(topics))
    return comment_dataset, topics

def load_from_csv():
    df = pd.read_csv("./data.csv")
    print(df)
    return df

if __name__ == "__main__":
    comment_list, topic = load_comment_list()

    
    df = pd.DataFrame({"id": list(range(len(comment_list))), "comment": comment_list, "topic": topic})
    print(df)
    df.to_csv("./data.csv", index=False)

    df = load_from_csv()
    print(df)