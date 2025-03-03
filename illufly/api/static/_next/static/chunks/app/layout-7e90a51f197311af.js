(self.webpackChunk_N_E=self.webpackChunk_N_E||[]).push([[177,792],{41226:()=>{},85986:(e,t,s)=>{Promise.resolve().then(s.bind(s,11179))},11179:(e,t,s)=>{"use strict";s.r(t),s.d(t,{default:()=>y});var o=s(95155),a=s(12115);s(30347);var n=s(86828),r=s(27660),c=s(79114);let l=[r.L.post("".concat(n.J,"/auth/login"),async e=>{let{request:t}=e;try{let e=await t.json();if(!e)return c.c.json({detail:"请求参数错误"},{status:400});let{username:s,password:o}=e;if(!s||!o||"string"!=typeof s||"string"!=typeof o||""===s.trim()||""===o.trim())return c.c.json({detail:"用户名和密码不能为空"},{status:400});if("test"===s&&"test123"===o)return c.c.json({user_id:"mock-user-1",username:s,email:"test@example.com",role:["user"],device_id:"mock-device-1"});return c.c.json({detail:"用户名或密码错误"},{status:401})}catch(e){return c.c.json({detail:"无效的请求格式"},{status:400})}}),r.L.get("".concat(n.J,"/auth/profile"),()=>c.c.json({user_id:"mock-user-1",username:"test",email:"test@example.com",role:["user"],device_id:"mock-device-1"})),r.L.post("".concat(n.J,"/auth/logout"),()=>c.c.json({message:"退出成功"}))],d=0,i=()=>"msg-".concat(Date.now(),"-").concat(d++),u=[{model:"gpt-4o",block_type:"question",request_id:"req1",message_id:"msg-1",favorite_id:"",role:"user",text:"什么是 AI？",message_type:"text",created_at:17132352e5,completed_at:17132352e5},{model:"gpt-4o",block_type:"answer",request_id:"req2",message_id:"msg-2",favorite_id:"",role:"assistant",text:"AI 是...",message_type:"text",created_at:1713235202e3,completed_at:17132354e5},{model:"gpt-4o",block_type:"question",request_id:"req3",message_id:"msg-3",favorite_id:"",role:"user",text:"什么是 AI？",message_type:"text",created_at:1713235206e3,completed_at:1713235208e4},{model:"gpt-4o",block_type:"answer",request_id:"req4",message_id:"msg-4",favorite_id:"",role:"assistant",text:"AI 是...",message_type:"text",created_at:171323521e4,completed_at:1713235212e3}],h=[{thread_id:"thread-1",title:"关于 AI 的讨论",created_at:17132352e5},{thread_id:"thread-2",title:"你是什么模型？",created_at:17132352e5}],m=h.map(e=>e.thread_id),_=[r.L.post("".concat(n.J,"/chat/threads"),()=>{let e={thread_id:"thread-new",title:"新对话 ...",created_at:Date.now()};return c.c.json(e)}),r.L.get("".concat(n.J,"/chat/threads"),()=>c.c.json(h)),r.L.get("".concat(n.J,"/chat/threads/:threadId/messages"),e=>{let{params:t}=e,{threadId:s}=t;return"string"!=typeof s?c.c.json({error:"Thread ID is not a string"},{status:400}):m.includes(s)?"thread-1"===s?c.c.json(u):c.c.json(u.slice(0,2)):"thread-new"===s?c.c.json([]):c.c.json({error:"Thread not found"},{status:404})}),r.L.post("".concat(n.J,"/chat/messages/:requestId/favorite"),()=>c.c.json({})),r.L.post("".concat(n.J,"/chat/complete"),async e=>{let{request:t}=e;console.log("POST chat/complete >>> ",t);let s="req-".concat(Date.now()),o=["这是第一个","消息块，","它会被","分段发送。"];return new Response((e=>new ReadableStream({start(t){let a=0;console.log("create_stream >>> ",e);let n=()=>{if(a>=o.length){t.enqueue(new TextEncoder().encode("\n")),t.close();return}let r=a===o.length-1,c={model:"gpt-4o",block_type:"answer",request_id:s,message_id:r?"".concat(e,"-text"):"".concat(e,"-chunk"),favorite_id:"",role:"assistant",text:o[a],message_type:r?"text":"text_chunk",created_at:Date.now(),completed_at:Date.now()};t.enqueue(new TextEncoder().encode("data: ".concat(JSON.stringify(c),"\n\n"))),++a<o.length&&setTimeout(n,300)};n()}}))(i()),{status:200,headers:{"text-Type":"text/event-stream",Connection:"keep-alive","Cache-Control":"no-cache","Access-Control-Allow-Origin":"*"}})})];var g=s(2818);async function p(){if("enabled"!==g.env.NEXT_PUBLIC_API_MOCKING)return;console.log("[MSW] 开始初始化");let e=Date.now();try{let{setupWorker:t}=await Promise.all([s.e(779),s.e(299),s.e(563),s.e(420),s.e(804),s.e(256),s.e(19),s.e(694),s.e(269),s.e(889),s.e(432),s.e(592),s.e(331),s.e(271),s.e(30),s.e(173),s.e(473),s.e(376)]).then(s.bind(s,90750));await t(...l,..._).start({serviceWorker:{url:"/mockServiceWorker.js",options:{scope:"/"}},onUnhandledRequest:e=>(e.url.includes("/api/")&&console.warn("未mock的API请求:",e.method,e.url),"bypass")}),console.log("[MSW] 初始化完成，耗时 ".concat(Date.now()-e,"ms"))}catch(e){throw console.error("[MSW] 初始化失败:",e),e}}function y(e){let{children:t}=e,[s,n]=(0,a.useState)(!1),[r,c]=(0,a.useState)(null);return((0,a.useEffect)(()=>{let e=!0;return console.log("Layout useEffect触发"),(async()=>{try{console.time("MSW初始化耗时"),await p(),console.timeEnd("MSW初始化耗时"),e&&(console.log("MSW初始化完成，设置isReady"),n(!0))}catch(t){console.error("初始化捕获错误:",t),e&&c(t)}})(),()=>{console.log("清理Layout effect"),e=!1}},[]),r)?(0,o.jsx)("html",{lang:"zh",children:(0,o.jsx)("body",{children:(0,o.jsxs)("div",{style:{padding:20},children:[(0,o.jsx)("h1",{children:"初始化错误"}),(0,o.jsx)("pre",{children:r.message})]})})}):s?(0,o.jsx)("html",{lang:"zh",children:(0,o.jsx)("body",{children:t})}):(0,o.jsx)("html",{lang:"zh",children:(0,o.jsx)("body",{children:(0,o.jsx)("div",{style:{padding:20},children:"正在初始化应用..."})})})}},86828:(e,t,s)=>{"use strict";s.d(t,{J:()=>a,t:()=>n});var o=s(85521);let a="/api",n=e=>{e.response&&401===e.response.status?console.log("未授权，重定向到登录页"):console.log("API 请求错误:",e),o.default.push("/login")}},30347:()=>{}},e=>{var t=t=>e(e.s=t);e.O(0,[690,779,299,563,420,804,256,19,694,269,889,432,592,331,271,30,173,473,376,358],()=>t(85986)),_N_E=e.O()}]);