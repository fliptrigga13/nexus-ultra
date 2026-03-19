
// ══════════════════════════════════════════════════════════════════
// THREE.JS NEURAL MESH — performance-optimised, 30fps cap
// 120 nodes, connected by edges within CDIST, mouse gravity
// ══════════════════════════════════════════════════════════════════
(function(){
  var C = document.getElementById('neural-bg');
  if (!C || typeof THREE === 'undefined') return;
  var W = innerWidth, H = innerHeight;
  var scene  = new THREE.Scene();
  var cam    = new THREE.PerspectiveCamera(60, W/H, 1, 2000);
  cam.position.z = 500;
  var rend = new THREE.WebGLRenderer({canvas:C,alpha:true,antialias:true,powerPreference:'low-power'});
  rend.setSize(W,H);
  rend.setPixelRatio(window.devicePixelRatio || 1);
  rend.setClearColor(0,0);

  function rr(a,b){return a+Math.random()*(b-a);}
  var CYAN=new THREE.Color(0x00e5ff), PURP=new THREE.Color(0xbf00ff), GRN=new THREE.Color(0x00ff88);
  var N=180, nodes=[];
  for(var i=0;i<N;i++){
    var t=Math.random();
    nodes.push({x:rr(-W*.55,W*.55),y:rr(-H*.55,H*.55),z:rr(-220,80),
      vx:rr(-.18,.18),vy:rr(-.18,.18),vz:rr(-.04,.04),
      col:t>.88?PURP:(t>.78?GRN:CYAN),sz:t>.88?7:(t>.78?5:3.5),
      p:Math.random()*Math.PI*2,ps:rr(.5,1.2),isTensor:t>.88});
  }
  var pPos=new Float32Array(N*3),pCol=new Float32Array(N*3),pSz=new Float32Array(N);
  var pGeo=new THREE.BufferGeometry();
  var pPA=new THREE.BufferAttribute(pPos,3);pPA.setUsage(THREE.DynamicDrawUsage);
  var pCA=new THREE.BufferAttribute(pCol,3);pCA.setUsage(THREE.DynamicDrawUsage);
  var pSA=new THREE.BufferAttribute(pSz,1);pSA.setUsage(THREE.DynamicDrawUsage);
  pGeo.setAttribute('position',pPA);pGeo.setAttribute('color',pCA);pGeo.setAttribute('size',pSA);
  var pMat=new THREE.ShaderMaterial({
    vertexShader:'attribute float size;attribute vec3 color;varying vec3 vC;void main(){vC=color;vec4 mv=modelViewMatrix*vec4(position,1.);gl_PointSize=size*(460./-mv.z);gl_Position=projectionMatrix*mv;}',
    fragmentShader:'varying vec3 vC;void main(){vec2 uv=gl_PointCoord-.5;float d=length(uv);if(d>.5)discard;float c=smoothstep(.5,.18,d)+smoothstep(.5,0.,d)*.3;gl_FragColor=vec4(vC,c);}',
    blending:THREE.AdditiveBlending,depthTest:false,transparent:true
  });
  scene.add(new THREE.Points(pGeo,pMat));

  var CDIST=160,MAXL=N*6;
  var lPos=new Float32Array(MAXL*6),lCol=new Float32Array(MAXL*6);
  var lGeo=new THREE.BufferGeometry();
  var lPA=new THREE.BufferAttribute(lPos,3);lPA.setUsage(THREE.DynamicDrawUsage);
  var lCA=new THREE.BufferAttribute(lCol,3);lCA.setUsage(THREE.DynamicDrawUsage);
  lGeo.setAttribute('position',lPA);lGeo.setAttribute('color',lCA);
  var lSeg=new THREE.LineSegments(lGeo,new THREE.LineBasicMaterial({vertexColors:true,blending:THREE.AdditiveBlending,depthTest:false,transparent:true}));
  scene.add(lSeg);

  // ── Inject tiny background particles ─────────────────────
  var ptGeo = new THREE.BufferGeometry();
  var ptCount = 800; // lots of tiny grains
  var ptPos = new Float32Array(ptCount * 3);
  for(var i=0; i<ptCount*3; i+=3){
      ptPos[i] = rr(-W*1.5, W*1.5);
      ptPos[i+1] = rr(-H*1.5, H*1.5);
      ptPos[i+2] = rr(-500, 200); // deep background
  }
  ptGeo.setAttribute('position', new THREE.BufferAttribute(ptPos, 3));
  var ptMat = new THREE.PointsMaterial({
      size: 1.8,
      color: 0x00e5ff,
      transparent: true,
      opacity: 0.35,
      blending: THREE.AdditiveBlending,
      sizeAttenuation: true
  });
  window.ptSystem = new THREE.Points(ptGeo, ptMat);
  scene.add(window.ptSystem);
  // ─────────────────────────────────────────────────────────


  var mx=0,my=0,tcx=0,tcy=0;
  document.addEventListener('mousemove',function(e){mx=(e.clientX-W/2)*1.05;my=(e.clientY-H/2)*1.05;tcx=(e.clientX-W/2)*.06;tcy=(e.clientY-H/2)*.06;});
  window.addEventListener('resize',function(){W=innerWidth;H=innerHeight;cam.aspect=W/H;cam.updateProjectionMatrix();rend.setSize(W,H);});

  // 30fps cap to reduce GPU load
  var lastT=0, FPS_INTERVAL=1000/30;
  var clk=new THREE.Clock();
  function tick(now){
    requestAnimationFrame(tick);
    if(now-lastT<FPS_INTERVAL)return;
    lastT=now;
    var t=clk.getElapsedTime();
    cam.position.x+=(tcx-cam.position.x)*.025;
    cam.position.y+=(-tcy-cam.position.y)*.025;
    cam.lookAt(scene.position);
  if(window.ptSystem){ window.ptSystem.rotation.y += 0.0003; window.ptSystem.rotation.x += 0.00015; }

    for(var i=0;i<N;i++){
      var nd=nodes[i];nd.p+=nd.ps*.033;
      nd.x+=nd.vx;nd.y+=nd.vy;nd.z+=nd.vz;
      var dx=mx-nd.x,dy=my-nd.y,d2=dx*dx+dy*dy,R2=350*350;
      if(d2<R2&&d2>1){var s=.05*(1-Math.sqrt(d2)/350);nd.vx+=dx*s;nd.vy+=dy*s;}
      nd.vx*=.988;nd.vy*=.988;nd.vz*=.993;
      var sp=Math.sqrt(nd.vx*nd.vx+nd.vy*nd.vy);if(sp>.5){nd.vx*=.5/sp;nd.vy*=.5/sp;}
      var BX=W*.62,BY=H*.62;
      if(nd.x<-BX){nd.x=-BX;nd.vx=Math.abs(nd.vx);}if(nd.x>BX){nd.x=BX;nd.vx=-Math.abs(nd.vx);}
      if(nd.y<-BY){nd.y=-BY;nd.vy=Math.abs(nd.vy);}if(nd.y>BY){nd.y=BY;nd.vy=-Math.abs(nd.vy);}
      if(nd.z<-220){nd.z=-220;nd.vz=Math.abs(nd.vz);}if(nd.z>80){nd.z=80;nd.vz=-Math.abs(nd.vz);}
      var pf=1+Math.sin(nd.p)*.16+(nd.isTensor?Math.sin(t*2+i)*.12:0);
      pPos[i*3]=nd.x;pPos[i*3+1]=nd.y;pPos[i*3+2]=nd.z;
      pCol[i*3]=nd.col.r;pCol[i*3+1]=nd.col.g;pCol[i*3+2]=nd.col.b;
      pSz[i]=nd.sz*pf;
    }
    var li=0;
    for(var a=0;a<N&&li<MAXL;a++){var na=nodes[a];
      for(var b=a+1;b<N&&li<MAXL;b++){var nb=nodes[b];
        var ex=na.x-nb.x,ey=na.y-nb.y,ez=na.z-nb.z,ed=Math.sqrt(ex*ex+ey*ey+ez*ez);
        if(ed<CDIST){var al=(1-ed/CDIST)*1.2;
          var rc=(na.col.r+nb.col.r)*.5*al,gc=(na.col.g+nb.col.g)*.5*al,bc=(na.col.b+nb.col.b)*.5*al;
          var base=li*6;
          lPos[base]=na.x;lPos[base+1]=na.y;lPos[base+2]=na.z;lCol[base]=rc;lCol[base+1]=gc;lCol[base+2]=bc;
          lPos[base+3]=nb.x;lPos[base+4]=nb.y;lPos[base+5]=nb.z;lCol[base+3]=rc;lCol[base+4]=gc;lCol[base+5]=bc;
          li++;}}}
    for(var k=li;k<MAXL;k++){var b=k*6;lPos[b]=lPos[b+1]=lPos[b+2]=lPos[b+3]=lPos[b+4]=lPos[b+5]=0;}
    lGeo.setDrawRange(0,li*2);
    pPA.needsUpdate=true;pCA.needsUpdate=true;pSA.needsUpdate=true;
    lPA.needsUpdate=true;lCA.needsUpdate=true;
    rend.render(scene,cam);
  }
  requestAnimationFrame(tick);
})();

// ══════════════════════════════════════════════════════════════════
// PHYSARUM SLIME FLOW OBSERVATORY v4
// Dual-canvas: wall canvas (persistent) + pheromone canvas (decays)
// Physarum 3-sensor chemotaxis, mouse events on pheromone canvas
// ══════════════════════════════════════════════════════════════════
function setObs(mode, btn) {
  window.__obsMode = mode;
  document.querySelectorAll('.obs-btn').forEach(function(b){b.classList.remove('active');});
  if (btn) btn.classList.add('active');
  var lbl = document.getElementById('obs-mode-label');
  if (lbl) lbl.textContent = {source:'SPAWN',sink:'SAFE ZONE',fire:'FAULT',wall:'WALL'}[mode]||mode.toUpperCase();
}
function obsReset(){if(window.__obsResetFn)window.__obsResetFn();}

(function(){
  var pC = document.getElementById('obs-canvas');
  var wC = document.getElementById('obs-wall-canvas');
  if (!pC) return;
  var pX = pC.getContext('2d',{willReadFrequently:true});
  var wX = wC ? wC.getContext('2d') : null;
  var W,H, agents=[], spawnPt=null, exitPt=null;
  var frame=0, totalSv=0, totalLo=0, faultCt=0;
  window.__obsMode='source';

  function resize(){
    var wr=document.getElementById('obs-canvas-wrap');
    W=pC.width=wr.clientWidth; H=pC.height=wr.clientHeight;
    if(wC){wC.width=W;wC.height=H;}
    pX.fillStyle='#040608';pX.fillRect(0,0,W,H);
  }

  window.__obsResetFn=function(){
    agents=[];spawnPt=null;exitPt=null;frame=0;totalSv=0;totalLo=0;faultCt=0;
    resize();
    if(wX)wX.clearRect(0,0,W,H);
    var ids=['obs-cap','obs-count','obs-tensors','obs-faults','obs-frame'];
    ids.forEach(function(id){var e=document.getElementById(id);if(e)e.textContent='0';});
    var sv=document.getElementById('obs-surv');if(sv){sv.textContent='100%';sv.className='hud-val safe';}
    var sb=document.getElementById('obs-status-bar');
    if(sb){sb.textContent='VEILPIERCER: Awaiting Slime Flow deployment.';sb.className='';}
    document.querySelectorAll('.obs-btn').forEach(function(b){b.classList.remove('active');});
    var sp=document.getElementById('btn-spawn');if(sp)sp.classList.add('active');
    window.__obsMode='source';
    var ml=document.getElementById('obs-mode-label');if(ml)ml.textContent='SPAWN';
  };

  function hud(id,val){var e=document.getElementById(id);if(e)e.textContent=val;}

  // 3-sensor Physarum: sample wall canvas + pheromone canvas
  var SA=22.5*Math.PI/180, SD=26, RA=45*Math.PI/180;
  function sense(x,y){
    if(x<0||x>=W||y<0||y>=H)return 0;
    if(wX){var wd=wX.getImageData(x|0,y|0,1,1).data;if(wd[3]>100)return -999;}
    var d=pX.getImageData(x|0,y|0,1,1).data;
    if(d[0]>155&&d[1]<70)return -999;
    return (d[1]+d[2])*.5;
  }
  function spd(){var s=document.getElementById('obs-speed');return s?parseFloat(s.value):3;}

  function loop(){
    // Pheromone decay
    pX.fillStyle='rgba(4,6,8,0.08)';pX.fillRect(0,0,W,H);
    var speed=spd(), tc=0;

    // Spawn
    if(spawnPt&&agents.length<4500){
      var burst=Math.min(10,4500-agents.length);
      for(var i=0;i<burst;i++)agents.push({
        x:spawnPt.x+(Math.random()-.5)*22,y:spawnPt.y+(Math.random()-.5)*22,
        a:Math.random()*Math.PI*2,hp:100,isTensor:Math.random()>.88,age:0});
    }

    var saved=0,lost=0;
    for(var i=agents.length-1;i>=0;i--){
      var ag=agents[i];ag.age++;
      var sF=sense(ag.x+Math.cos(ag.a)*SD,     ag.y+Math.sin(ag.a)*SD);
      var sL=sense(ag.x+Math.cos(ag.a-SA)*SD,  ag.y+Math.sin(ag.a-SA)*SD);
      var sR=sense(ag.x+Math.cos(ag.a+SA)*SD,  ag.y+Math.sin(ag.a+SA)*SD);

      if(sF===-999&&sL===-999&&sR===-999){ag.a+=Math.PI+(Math.random()-.5)*.5;}
      else if(sF===-999){ag.a+=(sL>sR?-1:1)*(RA+(Math.random()*.25));ag.hp-=4;}
      else if(sL===-999){ag.a+=RA*.85;}
      else if(sR===-999){ag.a-=RA*.85;}
      else if(sF>sL&&sF>sR){ag.a+=(Math.random()-.5)*.06;}
      else if(sL>sR){ag.a-=RA*(.6+Math.random()*.35);}
      else if(sR>sL){ag.a+=RA*(.6+Math.random()*.35);}
      else{ag.a+=(Math.random()-.5)*RA;}

      if(exitPt){
        var te=Math.atan2(exitPt.y-ag.y,exitPt.x-ag.x),df=te-ag.a;
        while(df>Math.PI)df-=2*Math.PI;while(df<-Math.PI)df+=2*Math.PI;
        ag.a+=df*.032;
      }
      ag.x+=Math.cos(ag.a)*speed;ag.y+=Math.sin(ag.a)*speed;

      if(ag.x<0||ag.x>W||ag.y<0||ag.y>H||ag.hp<=0){agents.splice(i,1);lost++;totalLo++;continue;}

      var hp=ag.hp/100;
      if(ag.isTensor){tc++;
        pX.shadowBlur=4;pX.shadowColor='#bf00ff';
        pX.fillStyle='rgba(191,0,255,'+(0.45+hp*.55)+')';
        var s=2+(1-hp)*2.5;
        pX.beginPath();pX.moveTo(ag.x,ag.y-s);pX.lineTo(ag.x+s,ag.y);pX.lineTo(ag.x,ag.y+s);pX.lineTo(ag.x-s,ag.y);pX.closePath();pX.fill();
        pX.shadowBlur=0;
      }else{
        var r=Math.round((1-hp)*200),g=Math.round(hp*229),b=Math.round(hp*255);
        pX.fillStyle='rgba('+r+','+g+','+b+','+(0.6+hp*.25)+')';pX.fillRect(ag.x-1,ag.y-1,2.3,2.3);
      }
      if(exitPt&&Math.hypot(exitPt.x-ag.x,exitPt.y-ag.y)<28){agents.splice(i,1);saved++;totalSv++;continue;}
    }

    if(spawnPt){pX.strokeStyle='rgba(0,229,255,'+(0.4+.15*Math.sin(frame*.09))+')';pX.lineWidth=1.5;pX.beginPath();pX.arc(spawnPt.x,spawnPt.y,14+5*Math.sin(frame*.09),0,Math.PI*2);pX.stroke();}
    if(exitPt){pX.strokeStyle='rgba(0,255,136,'+(0.5+.2*Math.sin(frame*.07))+')';pX.lineWidth=2;pX.beginPath();pX.arc(exitPt.x,exitPt.y,18+6*Math.sin(frame*.06),0,Math.PI*2);pX.stroke();pX.fillStyle='rgba(0,255,136,.07)';pX.beginPath();pX.arc(exitPt.x,exitPt.y,24,0,Math.PI*2);pX.fill();}

    if(frame%45===0){
      var total=totalSv+totalLo||1,rate=Math.max(0,Math.round(totalSv/total*100));
      hud('obs-cap',saved);hud('obs-count',agents.length);hud('obs-tensors',tc);hud('obs-frame',frame);hud('obs-faults',faultCt);
      var sv=document.getElementById('obs-surv');
      if(sv){sv.textContent=rate+'%';sv.className='hud-val '+(rate>=70?'safe':rate>=40?'warn':'crit');}
      var sb=document.getElementById('obs-status-bar');
      if(sb){
        if(!spawnPt){sb.textContent='AWAITING DEPLOYMENT \u2014 Click SPAWN then click the canvas.';sb.className='';}
        else if(rate<40){sb.textContent='CRITICAL: '+(100-rate)+'% agent loss \u2014 LOCKDOWN recommended.';sb.className='critical';}
        else if(rate<70){sb.textContent='WARNING: Survivability '+rate+'% \u2014 tensor anomaly detected.';sb.className='warning';}
        else{sb.textContent='NOMINAL: '+rate+'% success \u2014 '+tc+' Tensor Cores active. Vera Rubin tolerance held.';sb.className='nominal';}
      }
    }
    frame++;requestAnimationFrame(loop);
  }

  // ── Pointer events on pheromone canvas ────────────────────────────
  function pos(e){var r=pC.getBoundingClientRect();return{x:(e.clientX-r.left)*(W/r.width),y:(e.clientY-r.top)*(H/r.height)};}
  var drawing=false,lastX=0,lastY=0;

  pC.addEventListener('mousedown',function(e){
    var p=pos(e), mode=window.__obsMode||'source';
    if(mode==='source'){spawnPt=p;}
    else if(mode==='sink'){exitPt=p;}
    else if(mode==='fire'){
      faultCt++;hud('obs-faults',faultCt);
      pX.shadowBlur=22;pX.shadowColor='#ff2200';pX.fillStyle='#ff2200';
      pX.beginPath();pX.arc(p.x,p.y,28,0,Math.PI*2);pX.fill();
      pX.shadowBlur=0;pX.fillStyle='rgba(255,60,0,.18)';
      pX.beginPath();pX.arc(p.x,p.y,52,0,Math.PI*2);pX.fill();
    }
  });
  pC.addEventListener('mousemove', function(e) {});
  pC.addEventListener('mouseup',function(){drawing=false;});
  pC.addEventListener('mouseleave',function(){drawing=false;});

  // speed slider
  var sl=document.getElementById('obs-speed');
  if(sl)sl.addEventListener('input',function(){var l=document.getElementById('obs-speed-label');if(l)l.textContent='Speed: '+parseFloat(this.value).toFixed(1)+' px/f';});

  window.addEventListener('resize',resize);
  setTimeout(function(){resize();loop();},300);
})();

// ══════════════════════════════════════════════════════════════════
// CUSTOM CURSOR
// ══════════════════════════════════════════════════════════════════
(function(){
  var dot=document.getElementById('cur'),ring=document.getElementById('cur-r');
  if(!dot||!ring)return;
  var rx=0,ry=0;
  document.addEventListener('mousemove',function(e){
    dot.style.left=e.clientX+'px';dot.style.top=e.clientY+'px';
    rx+=(e.clientX-rx)*.15;ry+=(e.clientY-ry)*.15;
    ring.style.left=rx+'px';ring.style.top=ry+'px';
  });
  document.querySelectorAll('a,button,[onclick]').forEach(function(el){
    el.addEventListener('mouseenter',function(){dot.style.transform='translate(-50%,-50%) scale(2.2)';ring.style.transform='translate(-50%,-50%) scale(1.6)';});
    el.addEventListener('mouseleave',function(){dot.style.transform='translate(-50%,-50%) scale(1)';ring.style.transform='translate(-50%,-50%) scale(1)';});
  });
})();

// ══════════════════════════════════════════════════════════════════
// SCROLL REVEAL
// ══════════════════════════════════════════════════════════════════
(function(){
  var items=document.querySelectorAll('.reveal');
  if(!items.length)return;
  var io=new IntersectionObserver(function(entries){
    entries.forEach(function(e){if(e.isIntersecting){e.target.classList.add('in');io.unobserve(e.target);}});
  },{threshold:0.07});
  items.forEach(function(el){io.observe(el);});
  setTimeout(function(){items.forEach(function(el){el.classList.add('in');});},1600);
})();
