from datetime import datetime
from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

def designation(role):
 return {"admin":"VD Lead / Administrator","co-lead":"Co-Lead","junior":"Junior Engineer","trainee":"Trainee Engineer"}.get(role,role)

def report(c,q,now):
 def get(k,d=''): return q.get(k,[d])[0]
 lo,hi,role=get('from'),get('to'),get('role','all')
 def within(d): return (not lo or d>=lo) and (not hi or d<=hi)
 members={r['id']:r for r in c.execute("SELECT * FROM members WHERE role!='admin'") if role=='all' or r['role']==role}
 sessions={(r['day'],r['session']):r for r in c.execute('SELECT * FROM sessions') if within(r['day'])}
 punches={(r['day'],r['session'],r['member']):r for r in c.execute('SELECT * FROM punches') if within(r['day']) and r['member'] in members}
 keys=set(punches)|{(r['day'],r['session'],r['member']) for r in c.execute('SELECT * FROM roster') if (r['day'],r['session']) in sessions and r['member'] in members}
 w=Workbook(); w.remove(w.active)
 def sheet(name,headers,widths):
  s=w.create_sheet(name); s.append(['Dr. AIT Motorsport Club | VD '+name]); s.merge_cells(start_row=1,start_column=1,end_row=1,end_column=len(headers)); s['A1'].font=Font(size=16,bold=True,color='FFFFFF'); s['A1'].fill=PatternFill('solid',fgColor='173653'); s.row_dimensions[1].height=28
  s.append([f'Report: {lo or "All dates"} to {hi or "Latest"} | {role} | IST']); s.merge_cells(start_row=2,start_column=1,end_row=2,end_column=len(headers)); s.append(headers)
  for cell in s[3]: cell.font=Font(bold=True,color='FFFFFF'); cell.fill=PatternFill('solid',fgColor='256083'); cell.alignment=Alignment(wrap_text=True)
  s.row_dimensions[3].height=30
  for i,v in enumerate(widths,1): s.column_dimensions[get_column_letter(i)].width=v
  s.freeze_panes='C4'; s.sheet_view.showGridLines=False; s.page_setup.orientation='landscape'; s.page_setup.paperSize=s.PAPERSIZE_A4; s.page_setup.fitToWidth=1; s.page_setup.fitToHeight=0; s.sheet_properties.pageSetUpPr.fitToPage=True; s.print_title_rows='1:3'; s.oddFooter.right.text='Administrator signature: __________________'; return s
 a=sheet('Attendance Register',['Member ID','Name','Role','Date','Day','Session','Scheduled start','Scheduled end','Punch IN','Punch OUT','Minutes','Late (min)','Status'],[15,23,12,13,14,10,15,15,14,14,12,12,20]); stats={m:[0,0,0,0] for m in members}
 for day,sn,m in sorted(keys):
  p=punches.get((day,sn,m)); s=sessions.get((day,sn)); st=datetime.fromisoformat(day+'T'+s['start']).replace(tzinfo=now.tzinfo) if s else None; en=datetime.fromisoformat(day+'T'+s['end']).replace(tzinfo=now.tzinfo) if s else None
  i=datetime.fromisoformat(p['inside']) if p else None; o=datetime.fromisoformat(p['outside']) if p and p['outside'] else None
  mins=round((o-i).total_seconds()/60,2) if o else None; late=round(max(0,(i-st).total_seconds()/60),2) if i and st else None
  if not en: status='Completed (unscheduled)' if o else 'Incomplete'
  elif now<en: status='In progress'
  elif not i: status='Absent'
  elif not o: status='Incomplete'
  elif max(0,(min(o,en)-max(i,st)).total_seconds())<.75*(en-st).total_seconds(): status='Partial'
  else: status='Late' if late>5 else 'Present'
  if en and now>=en:
   z=stats[m]; z[0]+=1; z[1]+=status in ('Present','Late'); z[2]+=status=='Absent'; z[3]+=status in ('Partial','Incomplete')
  a.append([m,members[m]['name'],designation(members[m]['role']),datetime.fromisoformat(day).date(),datetime.fromisoformat(day).strftime('%A'),sn,st.time() if st else None,en.time() if en else None,i.time() if i else None,o.time() if o else None,mins,late,status]); row=a.max_row; a.cell(row,4).number_format='dd/mm/yyyy'
  for col in range(7,11): a.cell(row,col).number_format='h:mm AM/PM'
  a.cell(row,13).fill=PatternFill('solid',fgColor={'Present':'D9EAD3','Absent':'F4CCCC','Late':'FFF2CC','Partial':'FFF2CC','Incomplete':'FCE5CD'}.get(status,'E2E8F0'))
 b=sheet('Attendance Summary',['Member ID','Name','Role','Ended sessions','Present incl. late','Absent','Partial / incomplete','Attendance %','Eligibility'],[15,25,13,17,18,12,20,16,18])
 for m,z in stats.items():
  r=b.max_row+1; b.append([m,members[m]['name'],designation(members[m]['role']),*z,f'=IF(D{r}=0,"",E{r}/D{r})',f'=IF(D{r}=0,"No sessions",IF(H{r}>=0.75,"Eligible","Below 75%"))']); b.cell(r,8).number_format='0.0%'
 d=sheet('Session Register',['Session','Date','Day','Topic','Instructor','Start IST','End IST'],[12,15,15,35,25,15,15])
 for (day,sn),s in sorted(sessions.items()): d.append([sn,day,datetime.fromisoformat(day).strftime('%A'),s['topic'],s['instructor'],s['start'],s['end']])
 e=sheet('Member Database',['Member ID','Name','USN','Year','Designation'],[18,30,23,12,18])
 for m,v in members.items(): e.append([m,v['name'],v['usn'],v['year'],designation(v['role'])])
 meeting=sheet('Meeting Attendance',['Meeting','Date','Member','IN','OUT','Minutes','Status'],[25,15,18,28,28,12,18]); ms={m:[0,0] for m in members}
 for r in c.execute('SELECT meetings.*,meeting_roster.member,meeting_punch.inside,meeting_punch.outside FROM meeting_roster JOIN meetings ON meetings.id=meeting_roster.mid LEFT JOIN meeting_punch ON meeting_punch.mid=meeting_roster.mid AND meeting_punch.member=meeting_roster.member'):
  if r['member'] not in members or not within(r['day']):continue
  st=datetime.fromisoformat(r['day']+'T'+r['start']).replace(tzinfo=now.tzinfo); en=datetime.fromisoformat(r['day']+'T'+r['end']).replace(tzinfo=now.tzinfo); i=datetime.fromisoformat(r['inside']) if r['inside'] else None; o=datetime.fromisoformat(r['outside']) if r['outside'] else None
  status='In progress' if now<en else 'Absent' if not i else 'Incomplete' if not o else 'Partial' if max(0,(min(o,en)-max(i,st)).total_seconds())<.75*(en-st).total_seconds() else 'Late' if (i-st).total_seconds()>300 else 'Present'
  if now>=en:ms[r['member']][0]+=1;ms[r['member']][1]+=status in ('Present','Late')
  meeting.append([r['title'],r['day'],r['member'],r['inside'],r['outside'],round((o-i).total_seconds()/60,2) if o and i else None,status])
 summary=sheet('Meeting Summary',['Member','Ended meetings','Qualified','Attendance %'],[20,20,20,20])
 for m,(n,k) in ms.items():summary.append([m,n,k,k/n if n else None]);summary.cell(summary.max_row,4).number_format='0.0%'
 for title,query,headers,widths in [('Work Done','SELECT member,title,category,submitted,status,remarks FROM work',['Member','Title','Category','Submitted','Status','Remarks'],[18,30,20,30,20,40]),('Technical Evaluation','SELECT member,skill,score,remarks,reviewer FROM evaluations',['Member','Skill','Score','Remarks','Reviewer'],[18,30,12,40,18]),('Activity Logs','SELECT member,actor,stamp,reason,changes FROM audit',['Member','Actor','Time','Reason','Changes'],[18,18,30,35,60])]:
  sh=sheet(title,headers,widths)
  for r in c.execute(query):
   if r[0] in members:sh.append(list(r))
 for s in w:
  s.auto_filter.ref=f'A3:{get_column_letter(s.max_column)}{s.max_row}'; s.print_area=f'A1:{get_column_letter(s.max_column)}{s.max_row}'
  for row in s.iter_rows(min_row=4):
   for cell in row:
    if cell.data_type=='f' and not (s==b and cell.column in (8,9)): cell.data_type='s'
 f=BytesIO(); w.save(f); return f.getvalue()
