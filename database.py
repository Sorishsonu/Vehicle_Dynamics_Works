import base64, io
from PIL import Image

def migrate(c):
    c.execute('CREATE TABLE IF NOT EXISTS profile_photos(member TEXT PRIMARY KEY, photo BLOB NOT NULL)')
    # Old biometric records are not used or copied without fresh consent.

def save_photo(c,member,value):
    raw=base64.b64decode(value,validate=True)
    if len(raw)>2000000: raise ValueError('Photo too large')
    with Image.open(io.BytesIO(raw)) as im:
        if im.width*im.height>16000000: raise ValueError('Photo too large')
        im.thumbnail((800,800)); out=io.BytesIO(); im.convert('RGB').save(out,'JPEG',quality=85)
    c.execute('INSERT OR REPLACE INTO profile_photos VALUES(?,?)',(member,out.getvalue()))
