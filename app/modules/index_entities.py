import nltk
import re
import time
import sys

from pymongo import MongoClient
from elasticsearch import Elasticsearch
from elasticsearch import helpers
from nltk.corpus import stopwords, wordnet

sent_detector = nltk.data.load('tokenizers/punkt/english.pickle')
###############################

client = MongoClient('localhost:27017')
es = Elasticsearch(
    [{'host': 'localhost', 'port': 9200}], timeout=30, max_retries=10, retry_on_timeout=True
)
es.cluster.health(wait_for_status='yellow', request_timeout=1)

def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False

def token_stopword_filter(word: str):
    filtered_word = ' '.join([t for t in word.split() if not is_number(t) and t not in stopwords.words('english')]) 
    filtered_word = re.sub(r'\[[^)]*\]', '', filtered_word)
    filtered_word = re.sub(u"[^\w\d'\s\-]+", '', filtered_word)
    return filtered_word

start = time.time()

filter_publications = ['arxiv']
existing_ids = []
for publication in filter_publications:
    query={"query": {"match": {"journal": {"query": publication}}}}
    for doc in helpers.scan(es, index="entities_smartpub", query=query, size=2000):
        existing_ids.append(doc['_id'])
        
print(len(existing_ids), 'entities already in index')
existing_ids_set = set(existing_ids)

sys.stdout.flush()
db = client.smartpub
pub = db.publications
all_entities = db.entities.find().batch_size(5000)
print('Entity set ready')
actions = []
count = 1
excluded = 1
for rr in all_entities:
    if 'word' not in rr:
        continue
        
    if count % 25000 == 0:
        print(count, "added to index")
        sys.stdout.flush()
        try:
            res = helpers.bulk(es, actions)
            actions = []
        except es.helpers.BulkIndexError:
            pass
        
    if excluded % 25000 == 0:
        print(excluded, "excluded from index")
        sys.stdout.flush()
        
    filtered_word = token_stopword_filter(rr['word'])
    _id = rr['paper_id'] + '_' + filtered_word
           
    if rr["Annotator"] in ['noise', 'other', 'software'] \
    or rr["clean"] in stopwords.words('english') \
    or wordnet.synsets(rr["clean"]) or rr['word'] == 'no_entities' \
    or len(rr['clean']) < 3 or _id in existing_ids_set:
        excluded = excluded + 1
        continue
    
    if 'Annotator_godmode' in rr:
        if rr['Annotator_godmode'] in ['noise', 'other', 'software']:
            excluded = excluded + 1
            continue    
        
    count = count + 1

    actions.append({
        "_index": "entities_smartpub",
        "_type": "entities",
        "_id": rr['paper_id'] + '_' + filtered_word,
        "paper_id": rr['paper_id'],
        "title": rr['title'],
        "year": rr['year'],
        "journal": rr['journal'],
        "word": filtered_word,
        "inwordNet": rr['in_wordnet'],
        "label": rr['label'],
        "PMIdata": rr['pmi_data'],
        "PMImethod": rr['pmi_method'],
        "filteredWord": rr['filtered_word'],
        "ds_similarity": round(float(rr['ds_similarity']), 4),
        "mt_similarity": round(float(rr['mt_similarity']), 4),
        "ds_sim_50": rr['ds_sim_50'],
        "ds_sim_60": rr['ds_sim_60'],
        "ds_sim_70": rr['ds_sim_70'],
        "ds_sim_80": rr['ds_sim_80'],
        "ds_sim_90": rr['ds_sim_90'],
        "mt_sim_50": rr['mt_sim_50'],
        "mt_sim_60": rr['mt_sim_60'],
        "mt_sim_70": rr['mt_sim_70'],
        "mt_sim_80": rr['mt_sim_80'],
        "mt_sim_90": rr['mt_sim_90'],
        "clean": token_stopword_filter(rr['clean']),
        "lower": token_stopword_filter(rr['word_lower']),
        "no_punkt": token_stopword_filter(rr['no_punkt']),
        "annotator": rr["Annotator"],
        "experiment": rr["experiment"]
    })
    

if len(actions) > 0:
    try:
        res = helpers.bulk(es, actions)
    except es.helpers.BulkIndexError:
        pass

print(count, 'entities added to index,', excluded, 'entities excluded and', len(existing_ids), 'previously in index')
print('Done in', time.time()-start, 'seconds')