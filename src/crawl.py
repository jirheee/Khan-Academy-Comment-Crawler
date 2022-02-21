from operator import le
import os
from pprint import pp
from pydoc_data.topics import topics
from time import sleep, time
from typing import Dict, List, Set, TypedDict
import selenium
from selenium import webdriver # type: ignore
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re
import json

from sympy import content
import util
from glob import glob

ka_base_url = "https://www.khanacademy.org/"

def get_first_order_topics(driver: webdriver.Chrome)->Set[str]:
    first_order_topic_links = set()

    driver.find_element_by_xpath('//button[@data-test-id="learn-menu-dropdown"]').click()
    
    topic_elements = driver.find_elements_by_xpath('//ul[@data-test-id="learn-menu"]//a')
    p = re.compile(ka_base_url+'([a-z]+|-{1})+')

    for topic in topic_elements:
        href = topic.get_attribute("href")
        m = p.match(href)
        if m and m.group() == href:
            first_order_topic_links.add(href)

    return list(first_order_topic_links.difference({
        "https://www.khanacademy.org/kids", 
        "https://www.khanacademy.org/sat", 
        "https://www.khanacademy.org/college-careers-more",
        }))

class SuborderTopicDict(TypedDict):
    href: str
    unit_hrefs: List[str]

## TODO: Refactor variable names
def get_suborder_topic_dict(driver: webdriver.Chrome, first_order_topic: str) -> Dict[str, SuborderTopicDict]:
    suborder_topic_dict: Dict[str, SuborderTopicDict] = {}

    print(first_order_topic)
    driver.get(first_order_topic)

    lecture_tags = driver.find_elements_by_xpath('//div[@data-slug]')
    lesson_href_re = re.compile(first_order_topic+"(/([a-z0-9]+|-|:)+){2}")
    for lecture_tag in lecture_tags:
        lecture_title_element = lecture_tag.find_element_by_xpath('.//h2//a')

        lesson_elements = lecture_tag.find_elements_by_xpath('.//a')
        unit_hrefs = []
        for lesson_element in lesson_elements:
            lesson_href = lesson_element.get_attribute("href")
            lesson_href_match = lesson_href_re.match(lesson_href)
            if lesson_href_match:
                unit_hrefs.append(lesson_href_match.group())
        suborder_topic_dict[lecture_title_element.text] = {"href": lecture_title_element.get_attribute("href"), "unit_hrefs": unit_hrefs}
    
    return suborder_topic_dict

def get_lecture_links(driver: webdriver.Chrome, suborder_topic_dict: SuborderTopicDict)->List[Dict[str, str]]:
    units: List[Dict[str, str]] = []

    for unit_href in suborder_topic_dict["unit_hrefs"]:
        driver.get(unit_href)

        lecture_links = {}
        lesson_cards = driver.find_elements_by_xpath('//div[@data-test-id="lesson-card"]')
        for lesson_card in lesson_cards:
            lesson_card_link = lesson_card.find_element_by_xpath('.//a[@data-test-id="lesson-card-link"]')
            lecture_links[lesson_card_link.text] = lesson_card_link.get_attribute("href")
            
        units.append(lecture_links)
    
    return units

def get_lectures(driver: webdriver.Chrome, first_order_links: Set[str]):
    for first_order_link in first_order_links:
        topic = first_order_link.split("/")[-1]
        first_order_path = f"./data/lectures/{topic}"
        os.makedirs(first_order_path)
        suborder_topic_dict = get_suborder_topic_dict(driver, first_order_link)
        for suborder_topic in suborder_topic_dict:
            print("suborder topic", suborder_topic)
            suborder_path = f"{first_order_path}/{util.string_to_snake_case_filename(suborder_topic)}.json"
            units = get_lecture_links(driver, suborder_topic_dict[suborder_topic])
            util.write_file(suborder_path, json.dumps(units, indent=4))

def get_content_links(driver: webdriver.Chrome, lecture_link: str):
    articles = []
    videos = []

    driver.get(lecture_link)

    content_elements = WebDriverWait(driver, 10).until(EC.presence_of_all_elements_located((By.XPATH, '//div[@aria-label="lesson table of contents"]//li[@role="presentation"]/div/a[@aria-current]')))

    href_set = set()
    for content_element in content_elements:
        href = content_element.get_attribute("href")
        if href in href_set:
            continue
        href_set.add(href)

        type_element = content_element.find_element_by_xpath('.//span[@aria-label]')
        content_type = type_element.get_attribute("aria-label")

        title_element = content_element.find_element_by_xpath('.//div[@title]')
        content_title = title_element.get_attribute("title")

        content_dict = {"title": content_title, "href": href}
        if content_type == "Video":
            videos.append(content_dict)
        elif content_type == "Article":
            articles.append(content_dict)
        else:
            print(f"this type of content has no comment! {content_title} {content_type}")

    return articles, videos


def get_article_video_links(driver: webdriver.Chrome):
    topic_directories = glob("./data/lectures/*")
    for i, topic_directory in enumerate(topic_directories):
        print(f"Topic {i+1}/{len(topic_directories)}")
        lecture_jsons = glob(f"{topic_directory}/*.json")
        content_topic_dir_path = topic_directory.replace("lectures", "contents")
        os.makedirs(content_topic_dir_path, exist_ok=True)
        for j, lecture_json in enumerate(lecture_jsons):
            print(f"|--Lecture {j+1}/{len(lecture_jsons)}")
            lecture_content_dict = []
            json_name = lecture_json.split("/")[-1]
            lecture_json_path = f"{content_topic_dir_path}/{json_name}"
            if os.path.isfile(lecture_json_path):
                print("** This lecture is already crawled **")
                continue
            with open(lecture_json, "r") as f:
                loaded_json = "".join([line.strip() for line in f.readlines()])
                lessons = json.loads(loaded_json)
                for k, lesson_dict in enumerate(lessons):
                    print(f"|----Lesson {k+1}/{len(lessons)}")
                    for lesson_name in lesson_dict:
                        articles, videos = get_content_links(driver, lesson_dict[lesson_name])
                        lecture_content_dict.append({"articles": articles, "videos": videos})
            util.write_file(lecture_json_path, json.dumps(lecture_content_dict,indent=4))

class LessonContentDict():
    def __init__(self, lecture_path, lesson_dict, lesson_index) -> None:
        self.articles = lesson_dict["articles"]
        self.videos = lesson_dict["videos"]
        self.lesson_path = f"{lecture_path.replace('/contents/', '/comments/')}/{lesson_index}.json"
    
    def crawl_article_comments(self):
        comment_dicts = []
        num_comments = 0
        try:
            for article_dict in self.articles:
                video_title = article_dict["title"]
                video_href = article_dict["href"]

                self.driver.get(video_href)

                is_show_more_exist = True
                while is_show_more_exist:
                    try:
                        show_more_button = WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.XPATH, '//div[@id="ka-uid-discussiontabbedpanel-0--tabbedpanel-content"]//button[@class="_1f0fvyce"]')))
                        show_more_button.click()
                    except:
                        print("All comments are revealed")
                        is_show_more_exist = False

                comment_elements = self.driver.find_elements_by_xpath('//div[@data-test-id="discussion-post"]//span[@class="_1glfes6x"]/span')
                comments = [comment_element.text for comment_element in comment_elements]
                num_comments += len(comments)
                comment_dicts.append({"title": video_title, "comments": comments})
        except:
            return comment_dicts, num_comments

        return comment_dicts, num_comments
        
    def crawl_video_comments(self):
        comment_dicts = []
        num_comments = 0
        try:
            for video_dict in self.videos:
                video_title = video_dict["title"]
                video_href = video_dict["href"]

                self.driver.get(video_href)

                is_show_more_exist = True
                while is_show_more_exist:
                    try:
                        show_more_button = WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.XPATH, '//div[@id="ka-uid-discussiontabbedpanel-0--tabbedpanel-content"]//button[@class="_1f0fvyce"]')))
                        show_more_button.click()
                    except:
                        print("All comments are revealed")
                        is_show_more_exist = False

                comment_elements = self.driver.find_elements_by_xpath('//div[@data-test-id="discussion-post"]//span[@class="_1glfes6x"]/span')
                comments = [comment_element.text for comment_element in comment_elements]
                num_comments += len(comments)
                comment_dicts.append({"title": video_title, "comments": comments})
        except:
            return comment_dicts, num_comments

        return comment_dicts, num_comments



    def crawl_comments(self):
        print(f"####### Start Crawling...: {self.lesson_path} #######")
        if os.path.isfile(self.lesson_path):
            print(f"{self.lesson_path} is already crawled")
            return 0
        self.driver = webdriver.Chrome(executable_path=chromedriver_path)
        print(f"{len(self.videos)} Videos / {len(self.articles)} Articles")
        print(f"Lesson Path: {self.lesson_path}")
        os.makedirs("/".join(self.lesson_path.split("/")[:-1]), exist_ok=True)
        article_comments, article_comments_num = self.crawl_article_comments()
        video_comments, video_comments_num = self.crawl_video_comments()
        util.write_file(self.lesson_path, json.dumps({"articles": article_comments, "videos":video_comments}, indent=2))

        print(f"### Crawled {article_comments_num} article comments {video_comments_num} video comments \ntotal {article_comments_num+video_comments_num} comments")
        try:
            self.driver.quit()
        except:
            pass
        return article_comments_num+video_comments_num

from multiprocessing import Pool

chromedriver_path = "../chromedriver" if "src" == os.getcwd().split("/")[-1] else "./chromedriver"

def get_lesson_dict_comment(arg):
    lesson_dict, print_str, lesson_index, path = arg
    print(print_str)
    crawled_comments = LessonContentDict(path, lesson_dict, lesson_index).crawl_comments()
    print(f"|----Crawled {crawled_comments} comments")
    return crawled_comments

def get_comments():
    topic_dirs = glob("./data/contents/*")
    total_comment_num = 0

    for topic_index, topic_dir in enumerate(topic_dirs):
        lecture_jsons = glob(f"{topic_dir}/*")
        for lecture_index, lecture_json in enumerate(lecture_jsons):
            with open(lecture_json, "r") as f:
                lesson_array = json.loads("".join([line.strip() for line in f.readlines()]))

                pool = Pool(processes=5)

                def get_print_str(lesson_index):
                    return f"|--Topic {topic_index+1}/{len(topic_dirs)} Lecture {lecture_index+1}/{len(lecture_jsons)} Lesson {lesson_index+1}/{len(lesson_array)}"

                args = [(lesson_dict, get_print_str(lesson_index), lesson_index, lecture_json.replace(".json", ""),) for lesson_index, lesson_dict in enumerate(lesson_array)]

                results = pool.map_async(get_lesson_dict_comment, args)

                results = results.get()

                total_comment_num += sum(results)
            print(f"Finished Lesture json {lecture_json} Total comments: {total_comment_num}")


def main():
    chromedriver_path = "../chromedriver" if "src" == os.getcwd().split("/")[-1] else "./chromedriver"

    # driver = webdriver.Chrome(executable_path=chromedriver_path)
    # driver.maximize_window()
    # driver.get(ka_base_url)

    sleep(1)

    """ 
    {
        'https://www.khanacademy.org/test-prep', 
        'https://www.khanacademy.org/humanities', 
        'https://www.khanacademy.org/economics-finance-domain', 
        'https://www.khanacademy.org/science', 
        'https://www.khanacademy.org/college-careers-more', 
        'https://www.khanacademy.org/computing', 
        'https://www.khanacademy.org/math',
        'https://www.khanacademy.org/ela'
    }
    """
    # first_order_links = get_first_order_topics(driver)

    # get_lectures(driver, first_order_links)

    # get_article_video_links(driver)

    get_comments()

    sleep(1)

    # driver.quit()


if __name__ == "__main__":
    main()