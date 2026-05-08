import fetch from './fetch.js';
import nodeFetch from 'node-fetch'; // 再次请出原生的 fetch
import jsdom from 'jsdom';
const { JSDOM } = jsdom;
import fs from 'fs';
import path, { resolve } from 'path';

import { fileURLToPath } from "url";
const __dirname = path.dirname(fileURLToPath(import.meta.url));

const delay = (ms) => new Promise(resolve => setTimeout(resolve, ms));

const getDate = () => {
	const add0 = num => num < 10 ? ('0' + num) : num;
	const date = new Date();
	return '' + date.getFullYear() + add0(date.getMonth() + 1) + add0(date.getDate());
}
const DATE = getDate();
const NEWS_PATH = path.join(__dirname, 'news');
const YEAR = DATE.substring(0, 4);
const MONTH = DATE.substring(4, 6);
const NEWS_YEAR_MONTH_PATH = path.join(NEWS_PATH, YEAR, MONTH);
const NEWS_MD_PATH = path.join(NEWS_YEAR_MONTH_PATH, DATE + '.md');
const README_PATH = path.join(__dirname, 'README.md');
const CATALOGUE_JSON_PATH = path.join(NEWS_PATH, 'catalogue.json');

console.log('DATE:', DATE);
console.log('NEWS_PATH:', NEWS_PATH);

const readFile = path => {
	return new Promise((resolve, reject) => {
		fs.readFile(path, {}, (err, data) => {
			if (err) reject(err);
			resolve(data);
		});
	});
};

const writeFile = (path, data) => {
	return new Promise((resolve, reject) => {
		fs.writeFile(path, data, err => {
			if (err) reject(err);
			resolve(true);
		});
	});
};

const getNewsList = async date => {
	const HTML = await fetch(`http://tv.cctv.com/lm/xwlb/day/${date}.shtml`);
	const fullHTML = `<!DOCTYPE html><html><head></head><body>${HTML}</body></html>`;
	const dom = new JSDOM(fullHTML);
	const nodes = dom.window.document.querySelectorAll('a');
	var links = [];
	nodes.forEach(node => {
		let link = node.href;
		if (!links.includes(link)) links.push(link);
	});
	const abstract = links.shift();
	console.log('成功获取新闻列表');
	return { abstract, news: links }
}

const getAbstract = async link => {
	if (!link) return '今日暂无简介链接';
	const HTML = await fetch(link);
	const dom = new JSDOM(HTML);
	const abstractNode = dom.window.document.querySelector(
		'#page_body > div.allcontent > div.video18847 > div.playingCon > div.nrjianjie_shadow > div > ul > li:nth-child(1) > p'
	);
	if (abstractNode && abstractNode.innerHTML) {
		console.log('成功获取新闻简介');
		return abstractNode.innerHTML.replaceAll('；', "；\n\n").replaceAll('：', "：\n\n");
	} else {
		return '今日新闻简介暂未发布或抓取失败。';
	}
}

const getNews = async links => {
	const linksLength = links.length;
	console.log('共', linksLength, '则新闻, 开始获取');
	var news = [];

	for (let i = 0; i < linksLength; i++) {
		const url = links[i];
		
        const html = await fetch(url);
		const dom = new JSDOM(html);
		const title = dom.window.document.querySelector('#page_body > div.allcontent > div.video18847 > div.playingVideo > div.tit')?.innerHTML?.replace('[视频]', '');
		const content = dom.window.document.querySelector('#content_area')?.innerHTML;
        
        let duration = '简讯无视频';

        // 第一步：挖出视频的专属身份证 guid
        const guidMatch = html.match(/var\s+guid\s*=\s*["']([a-zA-Z0-9]+)["']/i);
        
        if (guidMatch && guidMatch[1]) {
            const videoGuid = guidMatch[1];
            try {
                // 【终极方案】：调用央视底层 VDN 视频分发网络接口
                // 加上 client=html5 参数，它会乖乖返回最纯粹的 JSON 视频信息
                const vdnUrl = `https://vdn.apps.cntv.cn/api/getHttpVideoInfo.do?pid=${videoGuid}&client=html5`;
                const apiRes = await nodeFetch(vdnUrl, {
                    method: "GET",
                    headers: {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36",
                        "Referer": "https://tv.cctv.com/" 
                    }
                });
                
                const apiResText = await apiRes.text();
                const videoData = JSON.parse(apiResText);
                
                // VDN 接口里，总时长一定藏在 video.totalLength 里
                let totalLengthStr = videoData?.video?.totalLength || (videoData?.video?.chapters && videoData.video.chapters.length > 0 ? videoData.video.chapters[0].duration : "");
                
                if (totalLengthStr !== undefined && totalLengthStr !== null && totalLengthStr !== "") {
                    const strVal = String(totalLengthStr).trim();
                    
                    if (strVal.includes(':')) {
                        duration = strVal.startsWith('00:') ? strVal.substring(3) : strVal;
                    } else {
                        const totalSeconds = Math.round(Number(strVal));
                        if (!isNaN(totalSeconds) && totalSeconds > 0) {
                            const minutes = Math.floor(totalSeconds / 60);
                            const seconds = totalSeconds % 60;
                            duration = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
                        }
                    }
                }
            } catch (e) {
                console.log(`[提示] 接口未返回视频 [${videoGuid}] 的时长数据。`);
            }
        }

		news.push({ title, content, duration });
		console.count(`已获取: ${title} - 时长: ${duration}`);

        if (i < linksLength - 1) { 
            await delay(2000); 
        }
	}
    
	console.log('成功获取所有新闻');
	return news;
}

const newsToMarkdown = ({ date, abstract, news, links }) => {
	let mdNews = '';
	const newsLength = news.length;
	for (let i = 0; i < newsLength; i++) {
        const { title, content, duration } = news[i]; 
		const link = links[i];
		mdNews += `### ${title}\n\n**视频时长:** ${duration}\n\n${content}\n\n[查看原文](${link})\n\n`;
	}
	return `# 《新闻联播》 (${date})\n\n## 新闻摘要\n\n${abstract}\n\n## 详细新闻\n\n${mdNews}\n\n---\n\n(更新时间戳: ${new Date().getTime()})\n\n`;
}

const saveTextToFile = async (savePath, text) => {
	await writeFile(savePath, text);
}

const updateCatalogue = async ({ catalogueJsonPath, readmeMdPath, date, abstract }) => {
	await readFile(catalogueJsonPath).then(async data => {
		data = data.toString();
		let catalogueJson = JSON.parse(data || '[]');
		catalogueJson.unshift({ date, abstract });
		// 只保留最近30天的目录
		if (catalogueJson.length > 30) catalogueJson = catalogueJson.slice(0, 30);
		let textJson = JSON.stringify(catalogueJson);
		await writeFile(catalogueJsonPath, textJson);
	});
	console.log('更新 catalogue.json 完成');

	// 生成最近7天的新闻列表
	const year = date.substring(0, 4);
	const month = date.substring(4, 6);
	const recentDays = [];
	for (let i = 0; i < 7; i++) {
		const d = new Date();
		d.setDate(d.getDate() - i);
		const ds = d.getFullYear().toString() +
			(d.getMonth() + 1).toString().padStart(2, '0') +
			d.getDate().toString().padStart(2, '0');
		const y = ds.substring(0, 4);
		const m = ds.substring(4, 6);
		recentDays.push(`- [${ds}](./news/${y}/${m}/${ds}.md)`);
	}

	await readFile(readmeMdPath).then(async data => {
		data = data.toString();
		// 替换新闻列表部分（在 "## 新闻列表" 之后的内容）
		const marker = '## 新闻列表';
		const markerIndex = data.indexOf(marker);
		if (markerIndex >= 0) {
			const before = data.substring(0, markerIndex);
			const newText = before + marker + '\n\n' + recentDays.join('\n') + '\n';
			await writeFile(readmeMdPath, newText);
		}
	});
	console.log('更新 README.md 完成');
}

// ========== 程序执行入口 ==========
const newsList = await getNewsList(DATE);

await delay(2000); 
const abstract = await getAbstract(newsList.abstract);

await delay(2000); 
const news = await getNews(newsList.news);

const md = newsToMarkdown({
	date: DATE,
	abstract,
	news,
	links: newsList.news
});
// 确保年/月目录存在
fs.mkdirSync(NEWS_YEAR_MONTH_PATH, { recursive: true });
await saveTextToFile(NEWS_MD_PATH, md);
await updateCatalogue({ 
	catalogueJsonPath: CATALOGUE_JSON_PATH,
	readmeMdPath: README_PATH,
	date: DATE,
	abstract: abstract
});
console.log('全部成功, 程序结束');
