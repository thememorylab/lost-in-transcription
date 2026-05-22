import argparse, base64, io, json, os, re, sys, time
from pathlib import Path
from dotenv import load_dotenv
import anthropic
from PIL import Image

MODEL = "claude-opus-4-7"
MAX_TOKENS = 4096
MAX_PX = 3000
NUM_STRIPS = 6
LINE_OVERLAP = 0.15

SYSTEM_PROMPT = (
    "You are a specialist in detecting underlining in 19th century Norwegian and Danish handwritten letters.\n\n"
    "You will receive a HORIZONTAL STRIP of a handwritten letter.\n\n"
    
    "WHAT UNDERLINING LOOKS LIKE:\n"
    "- A deliberate horizontal stroke drawn beneath a word, sitting below the text baseline\n"
    "- Visually separate from the letters — clear gap between letter bottoms and the line\n"
    "- Runs beneath most of the word's width\n"
    "- May be slightly curved following the handwriting baseline\n\n"
    
    "HOW TO DISTINGUISH REAL UNDERLINES FROM FALSE POSITIVES:\n"
    "- Descenders (tails of g, j, p, y, f) go DOWN from letters — NOT underlines\n"
    "- A stroke coming from a letter in the LINE ABOVE is a descender — NOT an underline\n"
    "- Real underlines have a clear gap from ALL letters both above and below\n"
    "- Bold or heavily written words where thick ink spreads below the baseline are NOT underlined\n"
    "- A strikethrough or heavy mark through the letters is NOT an underline\n"
    "- Ink bleed or paper texture beneath words is NOT an underline\n"
    "- Lines beneath names in closing position (after Deres, Deres hengivne, Med vennlig hilsen) are signature flourishes — exclude them\n"
    "- Personal names (first name + surname combinations) appearing at the bottom of a letter are almost always signatures — any line beneath them is a flourish, not underlining\n"
    "- Roman numerals and section headings with lines beneath them are formatting markers — NOT underlining\n\n"
    
    "CRITICAL BOUNDARY RULE:\n"
    "Report ONLY the words where you can SEE the line physically beneath them.\n"
    "The text entry must stop at the LAST WORD where the line is visible.\n"
    "Do NOT include words that come after the line ends, even if they are part of the same phrase.\n"
    "Ask yourself for each word: Can I see the line under THIS specific word? If no — do not include it.\n\n"
    
    "MULTI-WORD UNDERLINES:\n"
    "- If ONE continuous unbroken line runs under multiple consecutive words, report ALL as ONE entry\n"
    "- If there is ANY visible gap or break between underlines, they are SEPARATE instances\n"
    "- Do NOT split a continuous underline into separate entries\n"
    "- Do NOT merge separate underlines into one entry\n\n"
    
    "SELF-CHECK BEFORE REPORTING:\n"
    "Before including any word: can I see the line physically beneath THIS word?\n"
    "Before merging words: is the line truly continuous with no gap?\n"
    "If you have found more than 5 underlinings in one strip, review each one again carefully before reporting — high counts are usually a sign of false positives in difficult documents."
)

STRIP_PROMPT = (
    "This is strip {strip_num} of {total_strips} from a handwritten letter.\n\n"
    "XML transcription for exact word spelling:\n"
    "{xml_content}\n\n"
    "For each word in this strip, examine the space BELOW it:\n\n"
    
    "STEP 1 - IS THERE A LINE?\n"
    "Is there a horizontal line beneath the word, separate from the letters? -> candidate\n"
    "Does the line come from a descender of the line ABOVE? -> DISCARD\n"
    "Is there a visible gap between the letters and the line? -> confirm\n"
    "Is the word written in heavy/bold ink where ink spreads below? -> DISCARD\n\n"
    
    "STEP 2 - WHERE DOES THE LINE END?\n"
    "For every confirmed underline, find the EXACT last word the line runs beneath.\n"
    "Stop there. Do not include any word after the line ends.\n"
    "Check each following word individually: Does the line run beneath THIS word?\n"
    "The moment the answer is no - stop.\n\n"
    
    "STEP 3 - IS IT ONE UNDERLINE OR SEVERAL?\n"
	"Look carefully at the space BETWEEN words for gaps in the line.\n"
	"Is the line continuous with NO gap between words? -> one entry, spans_multiple_words: true\n"
	"Is there a visible gap or break between the underline of one word and the next? -> SEPARATE entries, even if the words form a logical phrase\n"
	"Example: if 'bis', 'auf' and 'weiteres' each have their own separate line beneath them -> three separate entries\n"
	"Example: if 'stormer' has a line and 'regner' has a line but 'og' between them has NO line -> two separate entries: 'stormer' and 'regner'\n"
	"IMPORTANT: A word between two underlined words is NOT underlined unless you can see a line beneath it too\n"
	"Example: if 'hverken har lyst eller evne' has one unbroken line beneath all words -> one entry\n\n"
   
    "STEP 4 - SIGNATURE CHECK\n"
	"Is this a personal name (first name + surname) appearing near the bottom of the letter? -> DISCARD as signature\n"
	"Does a line beneath a name sweep broadly or curve upward at the ends? -> DISCARD as signature flourish\n"
	"Any detection marked uncertain that appears to be a name -> DISCARD\n\n"
	
    "Use exact spelling from the XML for the text field.\n\n"
    "Return ONLY raw JSON with no markdown, no fences, no explanation:\n"
    '{{"underlinings": [{{"text": "exact words", "spans_multiple_words": false, "spans_line_break": false, "position": "strip {strip_num}", "confidence": "certain"}}]}}\n\n'
    
    "CONFIDENCE: certain, probable, uncertain\n"
    'If nothing found: {{"underlinings": []}}'
)

def extract_text(xml_content):
    lines = re.findall(r'<Unicode>(.*?)</Unicode>', xml_content, re.DOTALL)
    return '\n'.join(lines)


def encode_image(p):
    img = Image.open(p)
    w, h = img.size
    if w > MAX_PX or h > MAX_PX:
        ratio = min(MAX_PX/w, MAX_PX/h)
        img = img.resize((int(w*ratio), int(h*ratio)), Image.LANCZOS)
        print(f"     [resized {w}x{h} -> {img.size[0]}x{img.size[1]}]")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return base64.standard_b64encode(buf.getvalue()).decode(), img


def slice_image(img):
    w, h = img.size
    strip_h = h // NUM_STRIPS
    overlap = int(strip_h * LINE_OVERLAP)
    strips = []
    for i in range(NUM_STRIPS):
        top = max(0, i * strip_h - overlap)
        bottom = min(h, (i + 1) * strip_h + overlap)
        if i == 0:
            bottom = min(h, bottom + int(strip_h * 0.2))
        strip = img.crop((0, top, w, bottom))
        buf = io.BytesIO()
        strip.save(buf, format="JPEG", quality=95)
        strips.append(base64.standard_b64encode(buf.getvalue()).decode())
    return strips


def find_pairs(folder):
    jpegs = {p.stem: p for p in folder.glob("*.jpg")}
    jpegs.update({p.stem: p for p in folder.glob("*.jpeg")})
    xmls = {p.stem: p for p in folder.glob("*.xml")}
    common = sorted(set(jpegs) & set(xmls))
    if not common:
        sys.exit("No matching pairs found.")
    only_jpg = set(jpegs) - set(xmls)
    only_xml = set(xmls) - set(jpegs)
    if only_jpg:
        print(f"[warning] JPEGs without XML: {sorted(only_jpg)}")
    if only_xml:
        print(f"[warning] XMLs without JPEG: {sorted(only_xml)}")
    return [(jpegs[s], xmls[s]) for s in common]


def parse_raw(raw):
    if not raw or not raw.strip():
        return {"underlinings": []}
    clean = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    clean = re.sub(r"\s*```$", "", clean).strip()
    try:
        parsed = json.loads(clean)
    except json.JSONDecodeError:
        return {"underlinings": []}
    if isinstance(parsed, list):
        parsed = {"underlinings": parsed}
    normalised = []
    for item in parsed.get("underlinings", []):
        if isinstance(item, str):
            normalised.append({
                "text": item,
                "spans_multiple_words": False,
                "spans_line_break": False,
                "position": "unknown",
                "confidence": "uncertain"
            })
        else:
            item.pop("purpose", None)
            normalised.append(item)
    parsed["underlinings"] = normalised
    return parsed


def call_api(client, img_b64, prompt):
    return client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": img_b64
            }},
            {"type": "text", "text": prompt}
        ]}]
    )


def deduplicate(underlinings):
    priority = {"certain": 3, "probable": 2, "uncertain": 1}
    sorted_u = sorted(underlinings, key=lambda x: len(x.get("text", "")), reverse=True)
    kept = []
    for candidate in sorted_u:
        candidate_text = candidate.get("text", "").strip().lower()
        already_covered = any(
            candidate_text in k.get("text", "").strip().lower() or
            k.get("text", "").strip().lower() in candidate_text
            for k in kept
        )
        if not already_covered:
            kept.append(candidate)
        else:
            for i, k in enumerate(kept):
                k_text = k.get("text", "").strip().lower()
                if candidate_text in k_text or k_text in candidate_text:
                    if priority.get(candidate.get("confidence"), 1) > priority.get(k.get("confidence"), 1):
                        kept[i] = candidate
                    break
    return kept


def analyse_pair(client, jpg, xml):
    print(f"  -> {jpg.name}")
    xml_content = xml.read_text(encoding="utf-8")
    plain_text = extract_text(xml_content)
    img_b64, img = encode_image(jpg)
    strips = slice_image(img)
    print(f"     [split into {len(strips)} strips]")
    all_underlinings = []
    for i, strip_b64 in enumerate(strips):
        prompt = STRIP_PROMPT.format(
            strip_num=i + 1,
            total_strips=len(strips),
            xml_content=plain_text[:3000]
        )
        try:
            r = call_api(client, strip_b64, prompt)
            raw = r.content[0].text
            parsed = parse_raw(raw)
            found = parsed.get("underlinings", [])
            if found:
                print(f"     strip {i+1}: {[u.get('text') for u in found]}")
            all_underlinings.extend(found)
            time.sleep(3)
        except Exception as e:
            print(f"     strip {i+1} error: {e}")
    deduped = deduplicate(all_underlinings)
    print(f"     [{len(deduped)} unique underlining(s) found]")
    for u in deduped:
        print(f"       - \"{u.get('text')}\" ({u.get('confidence')})")
    return {
        "file": jpg.stem,
        "model": MODEL,
        "underlinings": deduped,
        "usage_note": f"{len(strips)} API calls"
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--folder", required=True)
    p.add_argument("--output", default="results_claude.json")
    args = p.parse_args()
    folder = Path(args.folder).resolve()
    if not folder.is_dir():
        sys.exit(f"Error: '{folder}' is not a directory.")
    load_dotenv()
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("ANTHROPIC_API_KEY not set in .env file.")
    client = anthropic.Anthropic(api_key=api_key)
    pairs = find_pairs(folder)
    print(f"Found {len(pairs)} pairs\n")
    results, errors = [], []
    for jpg, xml in pairs:
        try:
            results.append(analyse_pair(client, jpg, xml))
            time.sleep(2)
        except Exception as e:
            print(f"  [ERROR] {jpg.name}: {e}")
            errors.append({"file": jpg.stem, "error": str(e)})
    out = {
        "model_used": MODEL,
        "total": len(pairs),
        "successful": len(results),
        "failed": len(errors),
        "results": results,
        "errors": errors
    }
    Path(args.output).write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nDone. Saved to {args.output}")
    if errors:
        print(f"[warning] {len(errors)} failed")


if __name__ == "__main__":
    main()
