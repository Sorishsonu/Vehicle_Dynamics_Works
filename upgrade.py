from urllib.parse import quote
import json, hmac

def migrate(c):
 for k in ('status','reporting'):
  if k not in [r[1] for r in c.execute('pragma table_info(members)')]: c.execute(f"ALTER TABLE members ADD COLUMN {k} TEXT DEFAULT '{'Active' if k=='status' else ''}'")
 c.executescript('CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,member TEXT,actor TEXT,stamp TEXT,reason TEXT,changes TEXT); CREATE TABLE IF NOT EXISTS corrections(id INTEGER PRIMARY KEY,member TEXT,request TEXT,stamp TEXT,status TEXT DEFAULT \'Pending\'); CREATE TABLE IF NOT EXISTS meeting_roster(mid INTEGER,member TEXT,PRIMARY KEY(mid,member));')
 c.execute('INSERT OR IGNORE INTO meeting_roster SELECT mid,member FROM meeting_punch')

fields=('name','usn','department','year','semester','email','phone','joined','reporting')
def controls(m,field,form,e):
 hidden=f'<input type="hidden" name="member" value="{e(m["id"])}">'
 return form('v12_edit',hidden+field('Member ID','newid',extra='required value="'+e(m['id'])+'"')+''.join(field(k.title(),k,extra='value="'+e(m[k])+'"') for k in fields)+'<label>Designation<select name="role">'+''.join(f'<option {"selected" if m["role"]==r else ""} value="{r}">{dict(trainee="Trainee Engineer",junior="Junior Engineer",**{"co-lead":"Co-Lead"})[r]}</option>' for r in ('trainee','junior','co-lead'))+'</select></label><label>Status<select name="status">'+''.join(f'<option {"selected" if m["status"]==r else ""}>{r}</option>' for r in ('Active','Suspended','Inactive'))+'</select></label>'+field('Reason','reason',extra='required')+'<button>Save official record</button>')+form('v12_photo',hidden+'<label>Change member photograph<input class="profile-file" type="file" accept="image/*" required></label><input type="hidden" name="photo"><button>Change photograph</button>')+form('v12_delete',hidden+'<p>Permanent deletion removes attendance, submissions and profile records.</p>'+field('Type member ID to confirm','confirm',extra='required')+field('Administrator password','pw','password','required')+field('Reason','reason',extra='required')+'<button class="out">Permanently delete member</button>')

def action(c,u,a,g,now,hashpw,save_photo):
 uid=u['id']; mid=g('member'); stamp=now().isoformat()
 if a=='v12_request':
  if not g('request').strip():return 'Enter correction request'
  c.execute('INSERT INTO corrections(member,request,stamp) VALUES(?,?,?)',(uid,g('request'),stamp));return 'Correction request submitted'
 if u['role']!='admin':return 'Permission denied'
 if a=='v12_resolve':
  c.execute("UPDATE corrections SET status='Reviewed' WHERE id=?",(g('rid'),));return 'Request marked reviewed'
 m=c.execute("SELECT * FROM members WHERE id=? AND role!='admin'",(mid,)).fetchone()
 if not m:return 'Member not found'
 refs={'punches':'member','roster':'member','logins':'member','reset_requests':'member','profile_photos':'member','meeting_punch':'member','meeting_roster':'member','work':'member','evaluations':'member','corrections':'member'}
 if a=='v12_photo':
  try:save_photo(c,mid,g('photo'));return 'Photograph changed'
  except Exception:return 'Invalid photograph'
 if not g('reason').strip():return 'Reason required'
 if a=='v12_edit':
  new=g('newid').strip(); vals={k:g(k) for k in fields}; vals.update(role=g('role'),status=g('status'))
  if not new or not vals['name'].strip() or vals['role'] not in ('trainee','junior','co-lead') or vals['status'] not in ('Active','Suspended','Inactive'):return 'Invalid details'
  if new!=mid and c.execute('SELECT 1 FROM members WHERE id=?',(new,)).fetchone():return 'ID already exists'
  changes={k:[m[k],v] for k,v in vals.items() if m[k]!=v}
  if new!=mid:
   changes['id']=[mid,new]
   for t,col in refs.items():c.execute(f'UPDATE {t} SET {col}=? WHERE {col}=?',(new,mid))
   for t in ('work','evaluations'):c.execute(f'UPDATE {t} SET reviewer=? WHERE reviewer=?',(new,mid))
  c.execute('UPDATE members SET id=?, '+','.join(k+'=?' for k in vals)+' WHERE id=?',(new,*vals.values(),mid))
  if vals['status']!='Active':c.execute('DELETE FROM logins WHERE member=?',(new,))
  mid=new
 elif a=='v12_delete':
  if g('confirm')!=mid or not hmac.compare_digest(u['pw'],hashpw(g('pw'),u['salt'])):return 'Confirmation failed'
  c.execute('DELETE FROM attachments WHERE work IN (SELECT id FROM work WHERE member=?)',(mid,))
  for t,col in refs.items():c.execute(f'DELETE FROM {t} WHERE {col}=?',(mid,))
  c.execute('DELETE FROM members WHERE id=?',(mid,));changes={'account':'Deleted'}
 else:return 'Unknown action'
 c.execute('INSERT INTO audit(member,actor,stamp,reason,changes) VALUES(?,?,?,?,?)',(mid,uid,stamp,g('reason'),json.dumps(changes)));return 'Official record updated'
