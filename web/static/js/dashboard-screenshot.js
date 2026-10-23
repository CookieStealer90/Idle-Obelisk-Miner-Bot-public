/* ============================================================
   dashboard-screenshot.js — Screenshot tab
   ============================================================ */

let scrAutoLoad=false, scrInterval=null;

function toggleScreenshotLoad(on){
  scrAutoLoad=on;
  if(on){refreshScreenshot();scrInterval=setInterval(refreshScreenshot,5000)}
  else{if(scrInterval)clearInterval(scrInterval);scrInterval=null;document.getElementById('scr-image').style.display='none';document.getElementById('scr-placeholder').style.display=''}
}

function refreshScreenshot(){
  if(!scrAutoLoad)return;
  const img=document.getElementById('scr-image');
  const ph=document.getElementById('scr-placeholder');
  const newImg=new Image();
  newImg.onload=()=>{img.src=newImg.src;img.style.display='';ph.style.display='none'};
  newImg.onerror=()=>{ph.textContent='Screenshot not available';ph.style.display='';img.style.display='none'};
  newImg.src='/api/screenshot?t='+Date.now();
}
