(self.webpackChunk_N_E=self.webpackChunk_N_E||[]).push([[177,792],{1226:()=>{},5986:(e,t,s)=>{Promise.resolve().then(s.bind(s,1179))},1179:(e,t,s)=>{"use strict";s.r(t),s.d(t,{default:()=>h});var a=s(5155),n=s(2115);s(347);var o=s(6828),r=s(7660),c=s(6733);r.L.post("".concat(o.J,"/auth/login"),async e=>{let{request:t}=e;try{let e=await t.json();if(!e)return c.c.json({detail:"请求参数错误"},{status:400});let{username:s,password:a}=e;if(!s||!a||"string"!=typeof s||"string"!=typeof a||""===s.trim()||""===a.trim())return c.c.json({detail:"用户名和密码不能为空"},{status:400});if("test"===s&&"test123"===a)return c.c.json({user_id:"mock-user-1",username:s,email:"test@example.com",role:["user"],device_id:"mock-device-1"});return c.c.json({detail:"用户名或密码错误"},{status:401})}catch(e){return c.c.json({detail:"无效的请求格式"},{status:400})}}),r.L.get("".concat(o.J,"/auth/profile"),()=>c.c.json({user_id:"mock-user-1",username:"test",email:"test@example.com",role:["user"],device_id:"mock-device-1"})),r.L.post("".concat(o.J,"/auth/logout"),()=>c.c.json({message:"退出成功"}));let l=[{request_id:"req1",message_id:"msg-1",favorite:null,role:"user",content:"什么是 AI？",message_type:"text",created_at:17132352e5,completed_at:17132352e5},{request_id:"req2",message_id:"msg-2",favorite:null,role:"assistant",content:"AI 是...",message_type:"text",created_at:1713235202e3,completed_at:17132354e5},{request_id:"req3",message_id:"msg-3",favorite:null,role:"user",content:"什么是 AI？",message_type:"text",created_at:1713235206e3,completed_at:1713235208e4},{request_id:"req4",message_id:"msg-4",favorite:null,role:"assistant",content:"AI 是...",message_type:"text",created_at:171323521e4,completed_at:1713235212e3}],d=[{thread_id:"thread-1",title:"关于 AI 的讨论",created_at:17132352e5},{thread_id:"thread-2",title:"你是什么模型？",created_at:17132352e5}],i=d.map(e=>e.thread_id);async function u(){}function h(e){let{children:t}=e,[s,o]=(0,n.useState)(!1),[r,c]=(0,n.useState)(null);return((0,n.useEffect)(()=>{let e=!0;return console.log("Layout useEffect触发"),(async()=>{try{console.time("MSW初始化耗时"),await u(),console.timeEnd("MSW初始化耗时"),e&&(console.log("MSW初始化完成，设置isReady"),o(!0))}catch(t){console.error("初始化捕获错误:",t),e&&c(t)}})(),()=>{console.log("清理Layout effect"),e=!1}},[]),r)?(0,a.jsx)("html",{lang:"zh",children:(0,a.jsx)("body",{children:(0,a.jsxs)("div",{style:{padding:20},children:[(0,a.jsx)("h1",{children:"初始化错误"}),(0,a.jsx)("pre",{children:r.message})]})})}):s?(0,a.jsx)("html",{lang:"zh",children:(0,a.jsx)("body",{children:t})}):(0,a.jsx)("html",{lang:"zh",children:(0,a.jsx)("body",{children:(0,a.jsx)("div",{style:{padding:20},children:"正在初始化应用..."})})})}r.L.post("".concat(o.J,"/chat/threads"),()=>{let e={thread_id:"thread-new",title:"",created_at:Date.now()};return c.c.json(e)}),r.L.get("".concat(o.J,"/chat/threads"),()=>c.c.json(d)),r.L.get("".concat(o.J,"/chat/threads/:threadId/messages"),e=>{let{params:t}=e,{threadId:s}=t;return"string"!=typeof s?c.c.json({error:"Thread ID is not a string"},{status:400}):i.includes(s)?"thread-1"===s?c.c.json(l):c.c.json(l.slice(0,2)):c.c.json({error:"Thread not found"},{status:404})}),r.L.post("".concat(o.J,"/chat/messages/:requestId/favorite"),()=>c.c.json({})),r.L.post("".concat(o.J,"/chat/threads/:threadId/ask"),async e=>{let{params:t,request:s}=e,{threadId:a}=t;console.log("POST chat/threads/:threadId/ask >>> ",a,await s.json());let n=["这是第一个","消息块，","它会被","分段发送。"];return new Response(new ReadableStream({start(e){let t=0,s="req-".concat(Date.now()),a="msg-".concat(Date.now(),"-1"),o="msg-".concat(Date.now(),"-2"),r=()=>{if(t>=n.length){e.enqueue(new TextEncoder().encode("\n")),e.close();return}let c=t===n.length-1,l={request_id:s,message_id:c?o:a,favorite:null,role:"assistant",content:n[t],message_type:c?"text":"text_chunk",created_at:Date.now(),completed_at:Date.now()};e.enqueue(new TextEncoder().encode("data: ".concat(JSON.stringify(l),"\n\n"))),++t<n.length&&setTimeout(r,300)};r()}}),{status:200,headers:{"Content-Type":"text/event-stream",Connection:"keep-alive","Cache-Control":"no-cache","Access-Control-Allow-Origin":"*"}})})},6828:(e,t,s)=>{"use strict";s.d(t,{J:()=>n,t:()=>o});var a=s(5521);let n="http://localhost:8000/api",o=e=>{e.response&&401===e.response.status?console.log("未授权，重定向到登录页"):console.log("API 请求错误:",e),a.default.push("/login")}},347:()=>{}},e=>{var t=t=>e(e.s=t);e.O(0,[690,779,299,563,420,804,256,19,694,269,889,432,592,331,271,30,173,473,376,358],()=>t(5986)),_N_E=e.O()}]);