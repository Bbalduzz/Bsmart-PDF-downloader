from Crypto.Util.Padding import unpad
from Crypto.Cipher import AES
from io import BytesIO
import requests
import umsgpack
import inquirer
import tarfile
import fitz

CREDS = ("your_mail_or_username", "your_password")

class BSmartAPI:
    BASE_URL = "https://www.bsmart.it/api/v5"
    KEY = b'\x1e\x00\xb8\x98s\x13\x9d!\x04\xedP\x1a\x8b\xf8h\x9b'

    def __init__(self):
        self.session = requests.Session()
        self.token = ''

    def _api_call(self, endpoint, method='GET', params=None, data=None, headers=None):
        url = f"{self.BASE_URL}/{endpoint}"
        response = self.session.request(method, url, params=params, data=data, headers=headers)
        response.raise_for_status()
        return response.json()

    def get_login_data(self, username, password):
        return self._api_call("session", method='POST', data={"password": password, "email": username})

    def get_library(self):
        return self._api_call("books", headers={"auth_token": self.token}, params={"per_page": 1000000, "page_thumb_size": "medium"})

    def get_preactivations(self):
        return self._api_call("books/preactivations", headers={"auth_token": self.token})

    def get_book_info(self, bookid, revision, operation):
        return self._api_call(f"books/{bookid}/{revision}/{operation}", headers={"auth_token": self.token}, params={"per_page": 1000000})

    def download_pack(self, url):
        r = self.session.get(url, stream=True)
        file = b""
        for data in r.iter_content(chunk_size=204800):
            file += data
        return tarfile.open(fileobj=BytesIO(file))

    def decrypt_file(self, file):
        header = umsgpack.unpackb(file.read(256).rstrip(b"\x00"))
        iv = file.read(16)
        obj = AES.new(self.KEY, AES.MODE_CBC, iv)
        dec = obj.decrypt(file.read(header["start"] - 256 - 16))
        return unpad(dec, AES.block_size) + file.read(), header["md5"]

    def login(self, username, password):
        login_data = self.get_login_data(username, password)
        if "auth_token" not in login_data:
            raise ValueError("There was and error while authentication: " + login_data["message"])
        self.token = login_data["auth_token"]

    def check_token(self, token):
        test = self.get_library(token)
        return "message" not in test

    def library(self):
        books = {str(book["id"]): {"title": book["title"], "revision": book["current_edition"]["revision"], "cover": book["cover"]} for book in self.get_library() if not book["liquid_text"]}
        return books

    def download_book(self, bookid, data):
        revision = data["revision"]
        resources = self.get_book_info(bookid, revision, "resources")
        resmd5 = {}
        for resource in resources:
            if resource["resource_type_id"] != 14:
                continue
            if pdf := next((asset for asset in resource["assets"] if asset["use"] == "page_pdf"), False):
                resmd5[pdf["md5"]] = resource["id"], resource["title"]

        pagespdf = {}
        asset_packs = self.get_book_info(bookid, revision, "asset_packs")
        pagespack = self.download_pack(next(pack["url"] for pack in asset_packs if pack["label"] == "page_pdf"))
        for member in pagespack.getmembers():
            if file := pagespack.extractfile(member):
                output, md5 = self.decrypt_file(file)
                pid, label = resmd5[md5]
                pagespdf[pid] = output

        pdf = fitz.Document()
        toc = []
        index = self.get_book_info(bookid, revision, "index")

        bookmarks = {entry["first_page"]["id"]: entry["title"] for entry in index if "first_page" in entry}
        for i, (pageid, pagepdfraw) in enumerate(sorted(pagespdf.items())):
            pagepdf = fitz.Document(stream=pagepdfraw, filetype="pdf")
            pdf.insert_pdf(pagepdf)
            if pageid in bookmarks:
                toc.append([1, bookmarks[pageid], i + 1])

        pdf.set_toc(toc)
        pdf.save(f"{data['title']}.pdf")

if __name__ == "__main__":
    bsmart = BSmartAPI()
    token = bsmart.login(*CREDS)
    books = bsmart.library()

    choice = inquirer.prompt([inquirer.List("book",message="Which book you want to download?",choices=[f"{book_data['title']}" for book_id, book_data in books.items()])])
    chosen_book_id = next((book_id for book_id, book_data in books.items() if book_data['title'] == choice["book"]), None)
    book_data = books[chosen_book_id] if chosen_book_id else "Book not found!"
    bsmart.download_book(chosen_book_id, book_data)
