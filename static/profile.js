document.querySelectorAll('form').forEach(form=>{
 const file=form.querySelector('.profile-file'); if(!file)return;
 form.addEventListener('submit',async e=>{
 if(form.dataset.ready==='yes'||!file.files.length)return;
 e.preventDefault();
 try {const img=await createImageBitmap(file.files[0]); const canvas=document.createElement('canvas'); const scale=Math.min(1,800/Math.max(img.width,img.height)); canvas.width=Math.max(1,Math.round(img.width*scale)); canvas.height=Math.max(1,Math.round(img.height*scale)); canvas.getContext('2d').drawImage(img,0,0,canvas.width,canvas.height); form.querySelector('[name=photo]').value=canvas.toDataURL('image/jpeg',0.85).split(',')[1]; img.close(); file.value=''; form.dataset.ready='yes'; form.requestSubmit();} catch(err){alert('Unable to read photo. Try a JPG or PNG.');}
 });
});

document.querySelectorAll('.work-files').forEach(input=>{const form=input.closest('form');form.addEventListener('submit',async e=>{if(form.dataset.workReady)return;e.preventDefault();try{const files=[...input.files];if(files.reduce((n,f)=>n+f.size,0)>50*1024*1024)throw Error('Maximum 50 MB total');const result=await Promise.all(files.map(f=>new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve({name:f.name,data:r.result.split(',')[1]});r.onerror=reject;r.readAsDataURL(f)})));form.querySelector('[name=files]').value=JSON.stringify(result);form.dataset.workReady='yes';form.requestSubmit()}catch(err){alert(err.message||'File upload failed')}})});
