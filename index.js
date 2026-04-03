import fetch from './fetch.js';
import jsdom from 'jsdom';
const { JSDOM } = jsdom;
import fs from 'fs';
import path, { resolve } from 'path';

import { fileURLToPath } from "url";
const __dirname = path.dirname(fileURLToPath(import.meta.url));

// 【新增】延迟函数，用来保护对方服务器，避免抓取太快被封
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
        
        // 🔥 【全新黑科技】先抓取视频的唯一身份证(guid)，再通过央视底层API获取真实时长！
        let duration = '简讯无视频';
        
        // 第一步：用正则在原始 HTML 里挖出 guid 
        const guidMatch = html.match(/var\s+guid\s*=\s*["']([a-zA-Z0-9]+)["']/i);
        
        if (guidMatch && guidMatch[1]) {
            const videoGuid = guidMatch[1];
            try {
                // 第二步：拿着 guid 去请求真实的视频详情 API
                const apiUrl = `https://api.cntv.cn/video/videoinfoByGuid?guid=${videoGuid}&serviceId=tvcctv`;
                
                // 注意：你项目中自定义的 fetch.js 返回的是文本格式
                let apiResText = await fetch(apiUrl);
                
                // 兼容处理：清理掉可能存在的 JSONP 包裹字符，只保留纯 JSON
                apiResText = apiResText.replace(/^[^{]+/, '').replace(/[^}]+$/, '');
                
                // 解析 JSON 数据
                const videoData = JSON.parse(apiResText);
                
                // 提取视频总时长
                if (videoData && videoData.video && videoData.video.totalLength) {
                    const totalSeconds = Math.round(Number(videoData.video.totalLength));
                    
                    // 将纯秒数转换为 "分:秒" 的格式
                    const minutes = Math.floor(totalSeconds / 60);
                    const seconds = totalSeconds % 60;
                    duration = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
                }
            } catch (e) {
                console.log(`获取/解析视频 [${videoGuid}] 时长失败:`, e.message);
            }
        }

		news.push({ title, content, duration });
		console.count('获取的新闻则数');

        // 【新增】每抓完一条，等待3秒钟，然后再抓下一条
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
        
        // 🔥 【排版修改】完全按照你的要求：标题下面紧跟着真实时长，然后是文本和原文链接
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

// 获取列表后等2秒
await delay(2000); 
const abstract = await getAbstract(newsList.abstract);

// 获取正文前等2秒
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
