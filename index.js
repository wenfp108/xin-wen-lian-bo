import fetch from './fetch.js'; 
import nodeFetch from 'node-fetch'; 
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
const DATE = "20260402";
const NEWS_PATH = path.join(__dirname, 'news');
const NEWS_MD_PATH = path.join(NEWS_PATH, DATE + '.md');
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
        
        // 第一步：挖出 guid 
        const guidMatch = html.match(/var\s+guid\s*=\s*["']([a-zA-Z0-9]+)["']/i);
        
        if (guidMatch && guidMatch[1]) {
            const videoGuid = guidMatch[1];
            try {
                // 第二步：请求接口
                const apiUrl = `https://api.cntv.cn/video/videoinfoByGuid?guid=${videoGuid}&serviceId=tvcctv`;
                const apiRes = await nodeFetch(apiUrl, {
                    method: "GET",
                    headers: {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36",
                        "Referer": "https://tv.cctv.com/" 
                    }
                });
                
                let apiResText = await apiRes.text();
                apiResText = apiResText.replace(/^[^{]+/, '').replace(/[^}]+$/, '');
                const videoData = JSON.parse(apiResText);
                
                // 拿到原始时长数据
                let totalLengthStr = videoData?.video?.totalLength || videoData?.time || videoData?.duration;
                
                if (totalLengthStr !== undefined && totalLengthStr !== null && totalLengthStr !== "") {
                    const strVal = String(totalLengthStr).trim();
                    
                    // 【修复核心】场景1：如果已经是带冒号的格式（例如 "03:43" 或 "00:03:43"），直接使用
                    if (strVal.includes(':')) {
                        // 如果是 "00:03:43"，只保留后面的 "03:43" 让他更整洁
                        duration = strVal.startsWith('00:') ? strVal.substring(3) : strVal;
                    } 
                    // 【修复核心】场景2：如果是纯数字秒数（例如 "223"），再做数学换算
                    else {
                        const totalSeconds = Math.round(Number(strVal));
                        if (!isNaN(totalSeconds) && totalSeconds > 0) {
                            const minutes = Math.floor(totalSeconds / 60);
                            const seconds = totalSeconds % 60;
                            duration = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
                        } else if (totalSeconds === 0) {
                             duration = '简讯无视频';
                        }
                    }
                }
            } catch (e) {
                console.log(`\n[报错] 抓取/解析视频 [${videoGuid}] 时长失败:`, e.message);
            }
        }

		news.push({ title, content, duration });
		console.count('获取的新闻则数');

        if (i < linksLength - 1) { 
            console.log(`等待 3 秒后抓取下一篇...`);
            await delay(3000); 
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
		let textJson = JSON.stringify(catalogueJson);
		await writeFile(catalogueJsonPath, textJson);
	});
	console.log('更新 catalogue.json 完成');
	await readFile(readmeMdPath).then(async data => {
		data = data.toString();
		let text = data.replace('', `\n- [${date}](./news/${date}.md)`)
		await writeFile(readmeMdPath, text);
	});
	console.log('更新 README.md 完成');
}

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
await saveTextToFile(NEWS_MD_PATH, md);
await updateCatalogue({ 
	catalogueJsonPath: CATALOGUE_JSON_PATH,
	readmeMdPath: README_PATH,
	date: DATE,
	abstract: abstract
});
console.log('全部成功, 程序结束');
