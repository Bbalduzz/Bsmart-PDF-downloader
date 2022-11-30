import requests
import msgpack
import tarfile
from io import BytesIO
from Cryptodome.Cipher import AES
from Cryptodome.Util.Padding import unpad
import fitz
import re
import lib

'''
This script is just an over-simplification (or so, most of the parts are taken from FelixFrog tool)
of @FelixFrog pdfgrabber tool. If u want something more complete and better made, check out his work 
https://github.com/FelixFrog/pdfgrabber
'''

key =  bytes([30, 0, 184, 152, 115, 19, 157, 33, 4, 237, 80, 26, 139, 248, 104, 155]) #'HgC4mHMTnSEE7VAai/homw=='

class URLS:
	user: str = 'https://www.bsmart.it/api/v5/user'
	lib: str = 'https://www.bsmart.it/api/v6/books?page_thumb_size=medium&per_page=25000'
	book: str = 'https://www.bsmart.it/api/v6/books/by_book_id/'
	books: str = 'https://api.bsmart.it/api/v5/books/'

url = input('Enter the book url:\n')
book_id = url.split('?')[0].removeprefix('https://my.bsmart.it/#/books/')
revision = url.split('?')[1].removeprefix('revision=')

def progress_bar(progress, total):
    percent = 100 * (progress / float(total))
    bar = '█' * int(percent) + '-' * (100 - int(percent))
    print(f'\r[+] Downloading pack... |{bar}| {percent:.2f}%', end='\r')

def decryptfile(file): # ez
	print('\r[+] Decrypting file...',end='\r')
	header = msgpack.unpackb(file.read(256).rstrip(b"\x00"))
	iv = file.read(16)
	obj = AES.new(key, AES.MODE_CBC, iv)
	dec = obj.decrypt(file.read(header[b"start"] - 256 - 16))
	return unpad(dec, AES.block_size) + file.read(), header[b"md5"].decode()

def downloadpack(url):
	r = requests.get(url, stream=True)
	length = int(r.headers.get("content-length", 1))
	file = b""
	n=0
	progress_bar(n/100, 100)
	for data in r.iter_content(chunk_size=102400):
		file += data
		n=n+1
		progress_bar(n/100, 100)
	return tarfile.open(fileobj=BytesIO(file))

with open('cookies.txt', 'r') as f:
	cookie = f.read()
	_bsw_session_v1_production = cookie.split(';')[0]

auth_token = requests.get(URLS.user, headers={'cookie':_bsw_session_v1_production}).json()['auth_token']
HEADERS = {'auth_token':auth_token}

#library = requests.get(URLS.lib, headers=HEADERS)
packs = requests.get(f'{URLS.books}/{book_id}/{revision}/asset_packs?per_page=1000000', headers=HEADERS).json() # --> page_pdf -> url
resources = requests.get(f"{URLS.books}/{book_id}/{revision}/resources?per_page=500", headers=HEADERS).json()
index = requests.get(f"{URLS.books}/{book_id}/{revision}/index", headers=HEADERS).json()

resmd5 = {}
for i in resources:
	if i["resource_type_id"] != 14:
		continue
	if pdf := next((j for j in i["assets"] if j["use"] == "page_pdf"), False):
		resmd5[pdf["md5"]] = i["id"], i["title"]

pagespdf, labelsmap = {}, {}
pagespack = downloadpack(next(i["url"] for i in packs if i["label"] == "page_pdf"))
for member in pagespack.getmembers():
	file = pagespack.extractfile(member)
	if file:
		output, md5 = decryptfile(file)
		pid, label = resmd5[md5]
		pagespdf[pid] = output
		labelsmap[pid] = label
	pdf = fitz.Document()
	toc, labels = [], []

bookmarks = {i["first_page"]["id"]:i["title"] for i in index}
for i, (pageid, pagepdfraw) in enumerate(sorted(pagespdf.items())):
	pagepdf = fitz.Document(stream=pagepdfraw, filetype="pdf")
	pdf.insert_pdf(pagepdf)
	labels.append(labelsmap[pageid])
	if pageid in bookmarks:
		toc.append([1, bookmarks[pageid], i + 1])
pdf.set_page_labels(lib.generatelabelsrule(labels))
pdf.set_toc(toc)

pdf.save(f'{book_id}.pdf')
