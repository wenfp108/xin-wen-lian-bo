import fs from 'fs';
import path from 'path';
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const NEWS_PATH = path.join(__dirname, 'news');
const README_PATH = path.join(__dirname, 'README.md');
const CATALOGUE_JSON_PATH = path.join(NEWS_PATH, 'catalogue.json');

// 设定你要保留的分界线：小于这个日期的全删掉
const CUTOFF_DATE = "20260401"; 

console.log(`--- 🧹 开始执行历史数据大扫除 (删除 ${CUTOFF_DATE} 之前的数据) ---`);

try {
    // 1. 无情删掉旧的 .md 新闻文件
    const oldFiles = fs.readdirSync(NEWS_PATH).filter(f => f.endsWith('.md') && f !== 'README.md');
    let delCount = 0;
    for (let file of oldFiles) {
        if (file.replace('.md', '') < CUTOFF_DATE) {
            fs.unlinkSync(path.join(NEWS_PATH, file));
            delCount++;
        }
    }
    console.log(`✅ 成功删除了 ${delCount} 个老旧的 Markdown 文件。`);

    // 2. 清理 catalogue.json 里的历史记录
    let catData = JSON.parse(fs.readFileSync(CATALOGUE_JSON_PATH, 'utf-8') || '[]');
    let newCatData = catData.filter(item => item.date >= CUTOFF_DATE);
    // 格式化保存，保持美观
    fs.writeFileSync(CATALOGUE_JSON_PATH, JSON.stringify(newCatData, null, 2));
    console.log(`✅ JSON 目录已净化，目前仅保留 ${newCatData.length} 条有效记录。`);

    // 3. 擦除 README.md 主页上的旧链接
    let readmeStr = fs.readFileSync(README_PATH, 'utf-8');
    let newReadmeLines = readmeStr.split('\n').filter(line => {
        let match = line.match(/- \[(\d{8})\]/);
        // 如果这行是个旧新闻链接，直接过滤掉不要
        if (match && match[1] < CUTOFF_DATE) return false; 
        return true; 
    });
    fs.writeFileSync(README_PATH, newReadmeLines.join('\n'));
    console.log(`✅ README.md 历史死链接清理完毕！`);
    
    console.log(`--- 大扫除完美结束！ ---\n`);
} catch (error) {
    console.log(`大扫除遇到问题: `, error.message);
}
