(self.webpackChunk_N_E=self.webpackChunk_N_E||[]).push([[376],{7825:e=>{e.exports=new Set([9757,9977,9994,9995,9996,9997,127877,127939,127940,127946,127947,128066,128067,128070,128071,128072,128073,128074,128075,128076,128077,128078,128079,128080,128102,128103,128104,128105,128110,128112,128113,128114,128115,128116,128117,128118,128119,128120,128124,128129,128130,128131,128133,128134,128135,128170,128373,128378,128400,128405,128406,128581,128582,128583,128587,128588,128589,128590,128591,128675,128692,128693,128694,128704,129304,129305,129306,129307,129308,129309,129310,129318,129328,129331,129332,129333,129334,129335,129336,129337,129340,129341,129342])},595:(e,t,n)=>{"use strict";n.d(t,{Ay:()=>h});let r="object"==typeof self?self:globalThis,i=(e,t)=>{let n=(t,n)=>(e.set(n,t),t),i=o=>{if(e.has(o))return e.get(o);let[s,l]=t[o];switch(s){case 0:case -1:return n(l,o);case 1:{let e=n([],o);for(let t of l)e.push(i(t));return e}case 2:{let e=n({},o);for(let[t,n]of l)e[i(t)]=i(n);return e}case 3:return n(new Date(l),o);case 4:{let{source:e,flags:t}=l;return n(new RegExp(e,t),o)}case 5:{let e=n(new Map,o);for(let[t,n]of l)e.set(i(t),i(n));return e}case 6:{let e=n(new Set,o);for(let t of l)e.add(i(t));return e}case 7:{let{name:e,message:t}=l;return n(new r[e](t),o)}case 8:return n(BigInt(l),o);case"BigInt":return n(Object(BigInt(l)),o)}return n(new r[s](l),o)};return i},o=e=>i(new Map,e)(0),{toString:s}={},{keys:l}=Object,a=e=>{let t=typeof e;if("object"!==t||!e)return[0,t];let n=s.call(e).slice(8,-1);switch(n){case"Array":return[1,""];case"Object":return[2,""];case"Date":return[3,""];case"RegExp":return[4,""];case"Map":return[5,""];case"Set":return[6,""]}return n.includes("Array")?[1,n]:n.includes("Error")?[7,n]:[2,n]},c=([e,t])=>0===e&&("function"===t||"symbol"===t),u=(e,t,n,r)=>{let i=(e,t)=>{let i=r.push(e)-1;return n.set(t,i),i},o=r=>{if(n.has(r))return n.get(r);let[s,u]=a(r);switch(s){case 0:{let t=r;switch(u){case"bigint":s=8,t=r.toString();break;case"function":case"symbol":if(e)throw TypeError("unable to serialize "+u);t=null;break;case"undefined":return i([-1],r)}return i([s,t],r)}case 1:{if(u)return i([u,[...r]],r);let e=[],t=i([s,e],r);for(let t of r)e.push(o(t));return t}case 2:{if(u)switch(u){case"BigInt":return i([u,r.toString()],r);case"Boolean":case"Number":case"String":return i([u,r.valueOf()],r)}if(t&&"toJSON"in r)return o(r.toJSON());let n=[],f=i([s,n],r);for(let t of l(r))(e||!c(a(r[t])))&&n.push([o(t),o(r[t])]);return f}case 3:return i([s,r.toISOString()],r);case 4:{let{source:e,flags:t}=r;return i([s,{source:e,flags:t}],r)}case 5:{let t=[],n=i([s,t],r);for(let[n,i]of r)(e||!(c(a(n))||c(a(i))))&&t.push([o(n),o(i)]);return n}case 6:{let t=[],n=i([s,t],r);for(let n of r)(e||!c(a(n)))&&t.push(o(n));return n}}let{message:f}=r;return i([s,{name:u,message:f}],r)};return o},f=(e,{json:t,lossy:n}={})=>{let r=[];return u(!(t||n),!!t,new Map,r)(e),r},h="function"==typeof structuredClone?(e,t)=>t&&("json"in t||"lossy"in t)?o(f(e,t)):structuredClone(e):(e,t)=>o(f(e,t))},1923:(e,t,n)=>{"use strict";n.d(t,{l:()=>h});var r=n(9407),i=n(9721),o=n(9424),s=n(9542),l=n(3262),a=n(2316);let c=function(e){let t=this.constructor.prototype,n=t[e],r=function(){return n.apply(r,arguments)};return Object.setPrototypeOf(r,t),r},u={}.hasOwnProperty;class f extends c{constructor(){super("copy"),this.Compiler=void 0,this.Parser=void 0,this.attachers=[],this.compiler=void 0,this.freezeIndex=-1,this.frozen=void 0,this.namespace={},this.parser=void 0,this.transformers=(0,l.S)()}copy(){let e=new f,t=-1;for(;++t<this.attachers.length;){let n=this.attachers[t];e.use(...n)}return e.data(i(!0,{},this.namespace)),e}data(e,t){return"string"==typeof e?2==arguments.length?(y("data",this.frozen),this.namespace[e]=t,this):u.call(this.namespace,e)&&this.namespace[e]||void 0:e?(y("data",this.frozen),this.namespace=e,this):this.namespace}freeze(){if(this.frozen)return this;for(;++this.freezeIndex<this.attachers.length;){let[e,...t]=this.attachers[this.freezeIndex];if(!1===t[0])continue;!0===t[0]&&(t[0]=void 0);let n=e.call(this,...t);"function"==typeof n&&this.transformers.use(n)}return this.frozen=!0,this.freezeIndex=Number.POSITIVE_INFINITY,this}parse(e){this.freeze();let t=w(e),n=this.parser||this.Parser;return p("parse",n),n(String(t),t)}process(e,t){let n=this;return this.freeze(),p("process",this.parser||this.Parser),d("process",this.compiler||this.Compiler),t?r(void 0,t):new Promise(r);function r(r,i){let s=w(e),l=n.parse(s);function a(e,n){e||!n?i(e):r?r(n):((0,o.ok)(t,"`done` is defined if `resolve` is not"),t(void 0,n))}n.run(l,s,function(e,t,r){if(e||!t||!r)return a(e);let i=n.stringify(t,r);"string"==typeof i||i&&"object"==typeof i&&"byteLength"in i&&"byteOffset"in i?r.value=i:r.result=i,a(e,r)})}}processSync(e){let t,n=!1;return this.freeze(),p("processSync",this.parser||this.Parser),d("processSync",this.compiler||this.Compiler),this.process(e,function(e,i){n=!0,(0,r.V)(e),t=i}),g("processSync","process",n),(0,o.ok)(t,"we either bailed on an error or have a tree"),t}run(e,t,n){m(e),this.freeze();let r=this.transformers;return n||"function"!=typeof t||(n=t,t=void 0),n?i(void 0,n):new Promise(i);function i(i,s){(0,o.ok)("function"!=typeof t,"`file` can’t be a `done` anymore, we checked");let l=w(t);r.run(e,l,function(t,r,l){let a=r||e;t?s(t):i?i(a):((0,o.ok)(n,"`done` is defined if `resolve` is not"),n(void 0,a,l))})}}runSync(e,t){let n,i=!1;return this.run(e,t,function(e,t){(0,r.V)(e),n=t,i=!0}),g("runSync","run",i),(0,o.ok)(n,"we either bailed on an error or have a tree"),n}stringify(e,t){this.freeze();let n=w(t),r=this.compiler||this.Compiler;return d("stringify",r),m(e),r(e,n)}use(e,...t){let n=this.attachers,r=this.namespace;if(y("use",this.frozen),null==e);else if("function"==typeof e)a(e,t);else if("object"==typeof e)Array.isArray(e)?l(e):o(e);else throw TypeError("Expected usable value, not `"+e+"`");return this;function o(e){if(!("plugins"in e)&&!("settings"in e))throw Error("Expected usable value but received an empty preset, which is probably a mistake: presets typically come with `plugins` and sometimes with `settings`, but this has neither");l(e.plugins),e.settings&&(r.settings=i(!0,r.settings,e.settings))}function l(e){let t=-1;if(null==e);else if(Array.isArray(e))for(;++t<e.length;)!function(e){if("function"==typeof e)a(e,[]);else if("object"==typeof e){if(Array.isArray(e)){let[t,...n]=e;a(t,n)}else o(e)}else throw TypeError("Expected usable value, not `"+e+"`")}(e[t]);else throw TypeError("Expected a list of plugins, not `"+e+"`")}function a(e,t){let r=-1,o=-1;for(;++r<n.length;)if(n[r][0]===e){o=r;break}if(-1===o)n.push([e,...t]);else if(t.length>0){let[r,...l]=t,a=n[o][1];(0,s.A)(a)&&(0,s.A)(r)&&(r=i(!0,a,r)),n[o]=[e,r,...l]}}}}let h=new f().freeze();function p(e,t){if("function"!=typeof t)throw TypeError("Cannot `"+e+"` without `parser`")}function d(e,t){if("function"!=typeof t)throw TypeError("Cannot `"+e+"` without `compiler`")}function y(e,t){if(t)throw Error("Cannot call `"+e+"` on a frozen processor.\nCreate a new processor first, by calling it: use `processor()` instead of `processor`.")}function m(e){if(!(0,s.A)(e)||"string"!=typeof e.type)throw TypeError("Expected node, got `"+e+"`")}function g(e,t,n){if(!n)throw Error("`"+e+"` finished async. Use `"+t+"` instead")}function w(e){return e&&"object"==typeof e&&"message"in e&&"messages"in e?e:new a.T(e)}},4732:(e,t,n)=>{"use strict";n.d(t,{o:()=>i});var r=n(7816);let i=function(e,t,n){let i=(0,r.C)(n);if(!e||!e.type||!e.children)throw Error("Expected parent node");if("number"==typeof t){if(t<0||t===Number.POSITIVE_INFINITY)throw Error("Expected positive finite number as index")}else if((t=e.children.indexOf(t))<0)throw Error("Expected child node or index");for(;++t<e.children.length;)if(i(e.children[t],t,e))return e.children[t]}},7816:(e,t,n)=>{"use strict";n.d(t,{C:()=>r});let r=function(e){if(null==e)return o;if("function"==typeof e)return i(e);if("object"==typeof e)return Array.isArray(e)?function(e){let t=[],n=-1;for(;++n<e.length;)t[n]=r(e[n]);return i(function(...e){let n=-1;for(;++n<t.length;)if(t[n].apply(this,e))return!0;return!1})}(e):i(function(t){let n;for(n in e)if(t[n]!==e[n])return!1;return!0});if("string"==typeof e)return i(function(t){return t&&t.type===e});throw Error("Expected function, string, or object as test")};function i(e){return function(t,n,r){var i;return!!(null!==(i=t)&&"object"==typeof i&&"type"in i&&e.call(this,t,"number"==typeof n?n:void 0,r||void 0))}}function o(){return!0}},1127:(e,t,n)=>{"use strict";n.d(t,{G1:()=>s,PW:()=>i,Y:()=>r});let r=o("end"),i=o("start");function o(e){return function(t){let n=t&&t.position&&t.position[e]||{};if("number"==typeof n.line&&n.line>0&&"number"==typeof n.column&&n.column>0)return{line:n.line,column:n.column,offset:"number"==typeof n.offset&&n.offset>-1?n.offset:void 0}}}function s(e){let t=i(e),n=r(e);if(t&&n)return{start:t,end:n}}},7159:(e,t,n)=>{"use strict";function r(e){return e&&"object"==typeof e?"position"in e||"type"in e?o(e.position):"start"in e||"end"in e?o(e):"line"in e||"column"in e?i(e):"":""}function i(e){return s(e&&e.line)+":"+s(e&&e.column)}function o(e){return i(e&&e.start)+"-"+i(e&&e.end)}function s(e){return e&&"number"==typeof e?e:1}n.d(t,{L:()=>r})},7795:(e,t,n)=>{"use strict";n.d(t,{dc:()=>o,_Z:()=>s,VG:()=>l});var r=n(7816);let i=[],o=!1,s="skip";function l(e,t,n,l){let a;"function"==typeof t&&"function"!=typeof n?(l=n,n=t):a=t;let c=(0,r.C)(a),u=l?-1:1;(function e(r,a,f){let h=r&&"object"==typeof r?r:{};if("string"==typeof h.type){let e="string"==typeof h.tagName?h.tagName:"string"==typeof h.name?h.name:void 0;Object.defineProperty(p,"name",{value:"node ("+r.type+(e?"<"+e+">":"")+")"})}return p;function p(){var h;let p,d,y,m=i;if((!t||c(r,a,f[f.length-1]||void 0))&&(m=Array.isArray(h=n(r,f))?h:"number"==typeof h?[!0,h]:null==h?i:[h])[0]===o)return m;if("children"in r&&r.children&&r.children&&m[0]!==s)for(d=(l?r.children.length:-1)+u,y=f.concat(r);d>-1&&d<r.children.length;){if((p=e(r.children[d],d,y)())[0]===o)return p;d="number"==typeof p[1]?p[1]:d+u}return m}})(e,void 0,[])()}},7885:(e,t,n)=>{"use strict";n.d(t,{YR:()=>i});var r=n(7795);function i(e,t,n,i){let o,s,l;"function"==typeof t&&"function"!=typeof n?(s=void 0,l=t,o=n):(s=t,l=n,o=i),(0,r.VG)(e,s,function(e,t){let n=t[t.length-1],r=n?n.children.indexOf(e):void 0;return l(e,r,n)},o)}},9083:(e,t,n)=>{"use strict";function r(e){let t=String(e),n=[];return{toOffset:function(e){if(e&&"number"==typeof e.line&&"number"==typeof e.column&&!Number.isNaN(e.line)&&!Number.isNaN(e.column)){for(;n.length<e.line;){let e=n[n.length-1],r=i(t,e),o=-1===r?t.length+1:r+1;if(e===o)break;n.push(o)}let r=(e.line>1?n[e.line-2]:0)+e.column-1;if(r<n[e.line-1])return r}},toPoint:function(e){if("number"==typeof e&&e>-1&&e<=t.length){let r=0;for(;;){let o=n[r];if(void 0===o){let e=i(t,n[r-1]);o=-1===e?t.length+1:e+1,n[r]=o}if(o>e)return{line:r+1,column:e-(r>0?n[r-1]:0)+1,offset:e};r++}}}}}function i(e,t){let n=e.indexOf("\r",t),r=e.indexOf("\n",t);return -1===r?n:-1===n||n+1===r?r:n<r?n:r}n.d(t,{C:()=>r})},2333:(e,t,n)=>{"use strict";n.d(t,{o:()=>i});var r=n(7159);class i extends Error{constructor(e,t,n){super(),"string"==typeof t&&(n=t,t=void 0);let i="",o={},s=!1;if(t&&(o="line"in t&&"column"in t?{place:t}:"start"in t&&"end"in t?{place:t}:"type"in t?{ancestors:[t],place:t.position}:{...t}),"string"==typeof e?i=e:!o.cause&&e&&(s=!0,i=e.message,o.cause=e),!o.ruleId&&!o.source&&"string"==typeof n){let e=n.indexOf(":");-1===e?o.ruleId=n:(o.source=n.slice(0,e),o.ruleId=n.slice(e+1))}if(!o.place&&o.ancestors&&o.ancestors){let e=o.ancestors[o.ancestors.length-1];e&&(o.place=e.position)}let l=o.place&&"start"in o.place?o.place.start:o.place;this.ancestors=o.ancestors||void 0,this.cause=o.cause||void 0,this.column=l?l.column:void 0,this.fatal=void 0,this.file,this.message=i,this.line=l?l.line:void 0,this.name=(0,r.L)(o.place)||"1:1",this.place=o.place||void 0,this.reason=this.message,this.ruleId=o.ruleId||void 0,this.source=o.source||void 0,this.stack=s&&o.cause&&"string"==typeof o.cause.stack?o.cause.stack:"",this.actual,this.expected,this.note,this.url}}i.prototype.file="",i.prototype.name="",i.prototype.reason="",i.prototype.message="",i.prototype.stack="",i.prototype.column=void 0,i.prototype.line=void 0,i.prototype.ancestors=void 0,i.prototype.cause=void 0,i.prototype.fatal=void 0,i.prototype.place=void 0,i.prototype.ruleId=void 0,i.prototype.source=void 0},2316:(e,t,n)=>{"use strict";n.d(t,{T:()=>c});var r=n(2333);let i={basename:function(e,t){let n;if(void 0!==t&&"string"!=typeof t)throw TypeError('"ext" argument must be a string');o(e);let r=0,i=-1,s=e.length;if(void 0===t||0===t.length||t.length>e.length){for(;s--;)if(47===e.codePointAt(s)){if(n){r=s+1;break}}else i<0&&(n=!0,i=s+1);return i<0?"":e.slice(r,i)}if(t===e)return"";let l=-1,a=t.length-1;for(;s--;)if(47===e.codePointAt(s)){if(n){r=s+1;break}}else l<0&&(n=!0,l=s+1),a>-1&&(e.codePointAt(s)===t.codePointAt(a--)?a<0&&(i=s):(a=-1,i=l));return r===i?i=l:i<0&&(i=e.length),e.slice(r,i)},dirname:function(e){let t;if(o(e),0===e.length)return".";let n=-1,r=e.length;for(;--r;)if(47===e.codePointAt(r)){if(t){n=r;break}}else t||(t=!0);return n<0?47===e.codePointAt(0)?"/":".":1===n&&47===e.codePointAt(0)?"//":e.slice(0,n)},extname:function(e){let t;o(e);let n=e.length,r=-1,i=0,s=-1,l=0;for(;n--;){let o=e.codePointAt(n);if(47===o){if(t){i=n+1;break}continue}r<0&&(t=!0,r=n+1),46===o?s<0?s=n:1!==l&&(l=1):s>-1&&(l=-1)}return s<0||r<0||0===l||1===l&&s===r-1&&s===i+1?"":e.slice(s,r)},join:function(...e){let t,n=-1;for(;++n<e.length;)o(e[n]),e[n]&&(t=void 0===t?e[n]:t+"/"+e[n]);return void 0===t?".":function(e){o(e);let t=47===e.codePointAt(0),n=function(e,t){let n,r,i="",o=0,s=-1,l=0,a=-1;for(;++a<=e.length;){if(a<e.length)n=e.codePointAt(a);else if(47===n)break;else n=47;if(47===n){if(s===a-1||1===l);else if(s!==a-1&&2===l){if(i.length<2||2!==o||46!==i.codePointAt(i.length-1)||46!==i.codePointAt(i.length-2)){if(i.length>2){if((r=i.lastIndexOf("/"))!==i.length-1){r<0?(i="",o=0):o=(i=i.slice(0,r)).length-1-i.lastIndexOf("/"),s=a,l=0;continue}}else if(i.length>0){i="",o=0,s=a,l=0;continue}}t&&(i=i.length>0?i+"/..":"..",o=2)}else i.length>0?i+="/"+e.slice(s+1,a):i=e.slice(s+1,a),o=a-s-1;s=a,l=0}else 46===n&&l>-1?l++:l=-1}return i}(e,!t);return 0!==n.length||t||(n="."),n.length>0&&47===e.codePointAt(e.length-1)&&(n+="/"),t?"/"+n:n}(t)},sep:"/"};function o(e){if("string"!=typeof e)throw TypeError("Path must be a string. Received "+JSON.stringify(e))}let s={cwd:function(){return"/"}};function l(e){return!!(null!==e&&"object"==typeof e&&"href"in e&&e.href&&"protocol"in e&&e.protocol&&void 0===e.auth)}let a=["history","path","basename","stem","extname","dirname"];class c{constructor(e){let t,n;t=e?l(e)?{path:e}:"string"==typeof e||function(e){return!!(e&&"object"==typeof e&&"byteLength"in e&&"byteOffset"in e)}(e)?{value:e}:e:{},this.cwd="cwd"in t?"":s.cwd(),this.data={},this.history=[],this.messages=[],this.value,this.map,this.result,this.stored;let r=-1;for(;++r<a.length;){let e=a[r];e in t&&void 0!==t[e]&&null!==t[e]&&(this[e]="history"===e?[...t[e]]:t[e])}for(n in t)a.includes(n)||(this[n]=t[n])}get basename(){return"string"==typeof this.path?i.basename(this.path):void 0}set basename(e){f(e,"basename"),u(e,"basename"),this.path=i.join(this.dirname||"",e)}get dirname(){return"string"==typeof this.path?i.dirname(this.path):void 0}set dirname(e){h(this.basename,"dirname"),this.path=i.join(e||"",this.basename)}get extname(){return"string"==typeof this.path?i.extname(this.path):void 0}set extname(e){if(u(e,"extname"),h(this.dirname,"extname"),e){if(46!==e.codePointAt(0))throw Error("`extname` must start with `.`");if(e.includes(".",1))throw Error("`extname` cannot contain multiple dots")}this.path=i.join(this.dirname,this.stem+(e||""))}get path(){return this.history[this.history.length-1]}set path(e){l(e)&&(e=function(e){if("string"==typeof e)e=new URL(e);else if(!l(e)){let t=TypeError('The "path" argument must be of type string or an instance of URL. Received `'+e+"`");throw t.code="ERR_INVALID_ARG_TYPE",t}if("file:"!==e.protocol){let e=TypeError("The URL must be of scheme file");throw e.code="ERR_INVALID_URL_SCHEME",e}return function(e){if(""!==e.hostname){let e=TypeError('File URL host must be "localhost" or empty on darwin');throw e.code="ERR_INVALID_FILE_URL_HOST",e}let t=e.pathname,n=-1;for(;++n<t.length;)if(37===t.codePointAt(n)&&50===t.codePointAt(n+1)){let e=t.codePointAt(n+2);if(70===e||102===e){let e=TypeError("File URL path must not include encoded / characters");throw e.code="ERR_INVALID_FILE_URL_PATH",e}}return decodeURIComponent(t)}(e)}(e)),f(e,"path"),this.path!==e&&this.history.push(e)}get stem(){return"string"==typeof this.path?i.basename(this.path,this.extname):void 0}set stem(e){f(e,"stem"),u(e,"stem"),this.path=i.join(this.dirname||"",e+(this.extname||""))}fail(e,t,n){let r=this.message(e,t,n);throw r.fatal=!0,r}info(e,t,n){let r=this.message(e,t,n);return r.fatal=void 0,r}message(e,t,n){let i=new r.o(e,t,n);return this.path&&(i.name=this.path+":"+i.name,i.file=this.path),i.fatal=!1,this.messages.push(i),i}toString(e){return void 0===this.value?"":"string"==typeof this.value?this.value:new TextDecoder(e||void 0).decode(this.value)}}function u(e,t){if(e&&e.includes(i.sep))throw Error("`"+t+"` cannot be a path: did not expect `"+i.sep+"`")}function f(e,t){if(!e)throw Error("`"+t+"` cannot be empty")}function h(e,t){if(!e)throw Error("Setting `"+t+"` requires `path` to be set too")}},6518:(e,t,n)=>{"use strict";n.d(t,{t:()=>r});let r={html:"http://www.w3.org/1999/xhtml",mathml:"http://www.w3.org/1998/Math/MathML",svg:"http://www.w3.org/2000/svg",xlink:"http://www.w3.org/1999/xlink",xml:"http://www.w3.org/XML/1998/namespace",xmlns:"http://www.w3.org/2000/xmlns/"}},5042:(e,t,n)=>{"use strict";n.d(t,{A:()=>i});let r={}.hasOwnProperty;function i(e,t){let n=t||{};function i(t,...n){let o=i.invalid,s=i.handlers;if(t&&r.call(t,e)){let n=String(t[e]);o=r.call(s,n)?s[n]:i.unknown}if(o)return o.call(this,t,...n)}return i.handlers=n.handlers||{},i.invalid=n.invalid,i.unknown=n.unknown,i}}}]);