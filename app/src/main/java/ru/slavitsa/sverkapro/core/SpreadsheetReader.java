package ru.slavitsa.sverkapro.core;

import org.xml.sax.Attributes;
import org.xml.sax.InputSource;
import org.xml.sax.helpers.DefaultHandler;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.Charset;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.regex.Pattern;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

import javax.xml.parsers.SAXParserFactory;

public final class SpreadsheetReader {
    private static final int MAX_INPUT_BYTES = 32 * 1024 * 1024;
    private static final int MAX_UNPACKED_BYTES = 96 * 1024 * 1024;
    private static final int MAX_ROWS = 200_000;
    private static final Set<Integer> BUILTIN_DATE_FORMATS = Set.of(
            14, 15, 16, 17, 18, 19, 20, 21, 22, 27, 30, 36, 45, 46, 47, 50, 57);
    private static final Pattern DATE_FORMAT_TOKEN = Pattern.compile("(^|[^a-z])(yy|dd|mm|hh|ss)", Pattern.CASE_INSENSITIVE);

    private SpreadsheetReader() {}

    public static TableData read(InputStream input, String sourceName) throws Exception {
        byte[] data = readLimited(input, MAX_INPUT_BYTES);
        String lower = sourceName == null ? "" : sourceName.toLowerCase(Locale.ROOT);
        if (isZip(data) || lower.endsWith(".xlsx")) return readXlsx(data, sourceName);
        if (isOle(data) || lower.endsWith(".xls")) return readXls(data, sourceName);
        if (lower.endsWith(".csv") || lower.endsWith(".txt")) return readCsv(data, sourceName);
        throw new IllegalArgumentException("Поддерживаются файлы XLS, XLSX и CSV.");
    }

    private static TableData readXlsx(byte[] data, String sourceName) throws Exception {
        Map<String, byte[]> entries = unzip(data);
        Map<String, String> actualNames = new HashMap<>();
        for (String name : entries.keySet()) actualNames.put(name.toLowerCase(Locale.ROOT), name);

        List<String> sharedStrings = new ArrayList<>();
        byte[] shared = getEntry(entries, actualNames, "xl/sharedstrings.xml");
        if (shared != null) parseSharedStrings(shared, sharedStrings);

        Set<Integer> dateStyles = new java.util.HashSet<>();
        byte[] styles = getEntry(entries, actualNames, "xl/styles.xml");
        if (styles != null) parseStyles(styles, dateStyles);

        List<SheetRef> sheets = parseWorkbook(entries, actualNames);
        if (sheets.isEmpty()) {
            List<String> names = new ArrayList<>(entries.keySet());
            Collections.sort(names);
            for (String name : names) {
                String normalized = name.toLowerCase(Locale.ROOT);
                if (normalized.startsWith("xl/worksheets/") && normalized.endsWith(".xml")) {
                    sheets.add(new SheetRef(name.substring(name.lastIndexOf('/') + 1, name.length() - 4), name));
                }
            }
        }

        for (SheetRef sheet : sheets) {
            byte[] xml = entries.get(sheet.path);
            if (xml == null) continue;
            List<List<Object>> matrix = parseSheet(xml, sharedStrings, dateStyles);
            if (hasMatrixValues(matrix)) return TableData.fromMatrix(sourceName, sheet.name, matrix);
        }
        throw new IllegalArgumentException("В XLSX не найден непустой лист с таблицей.");
    }

    private static TableData readXls(byte[] data, String sourceName) {
        OleFile ole = new OleFile(data);
        byte[] workbook = ole.readStream("Workbook", "Book");
        BiffWorkbook biff = new BiffWorkbook(workbook);
        return biff.readFirstTable(sourceName);
    }

    private static TableData readCsv(byte[] data, String sourceName) throws CharacterCodingException {
        String text;
        try {
            text = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(data)).toString();
        } catch (CharacterCodingException invalidUtf8) {
            text = Charset.forName("windows-1251").decode(ByteBuffer.wrap(data)).toString();
        }
        if (text.startsWith("\uFEFF")) text = text.substring(1);
        char delimiter = detectDelimiter(text);
        List<List<Object>> matrix = parseCsv(text, delimiter);
        return TableData.fromMatrix(sourceName, "CSV", matrix);
    }

    private static byte[] readLimited(InputStream input, int limit) throws IOException {
        try (InputStream in = input; ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[64 * 1024];
            int total = 0;
            int count;
            while ((count = in.read(buffer)) >= 0) {
                total += count;
                if (total > limit) throw new IOException("Файл превышает допустимый размер 32 МБ.");
                out.write(buffer, 0, count);
            }
            return out.toByteArray();
        }
    }

    private static boolean isZip(byte[] data) {
        return data.length >= 4 && data[0] == 'P' && data[1] == 'K';
    }

    private static boolean isOle(byte[] data) {
        byte[] magic = {(byte) 0xD0, (byte) 0xCF, 0x11, (byte) 0xE0, (byte) 0xA1, (byte) 0xB1, 0x1A, (byte) 0xE1};
        return data.length >= magic.length && Arrays.equals(Arrays.copyOf(data, magic.length), magic);
    }

    private static Map<String, byte[]> unzip(byte[] data) throws IOException {
        Map<String, byte[]> entries = new LinkedHashMap<>();
        int total = 0;
        try (ZipInputStream zip = new ZipInputStream(new ByteArrayInputStream(data))) {
            ZipEntry entry;
            byte[] buffer = new byte[32 * 1024];
            while ((entry = zip.getNextEntry()) != null) {
                if (entry.isDirectory()) continue;
                ByteArrayOutputStream out = new ByteArrayOutputStream();
                int count;
                while ((count = zip.read(buffer)) >= 0) {
                    total += count;
                    if (total > MAX_UNPACKED_BYTES) throw new IOException("Содержимое XLSX слишком велико.");
                    out.write(buffer, 0, count);
                }
                entries.put(entry.getName(), out.toByteArray());
            }
        }
        return entries;
    }

    private static byte[] getEntry(Map<String, byte[]> entries, Map<String, String> names, String wanted) {
        String actual = names.get(wanted.toLowerCase(Locale.ROOT));
        return actual == null ? null : entries.get(actual);
    }

    private static void parseSharedStrings(byte[] xml, List<String> output) throws Exception {
        parseXml(xml, new DefaultHandler() {
            boolean inSi;
            boolean inText;
            StringBuilder value;

            @Override public void startElement(String uri, String localName, String qName, Attributes attributes) {
                String name = xmlName(localName, qName);
                if ("si".equals(name)) {
                    inSi = true;
                    value = new StringBuilder();
                } else if (inSi && "t".equals(name)) {
                    inText = true;
                }
            }

            @Override public void characters(char[] ch, int start, int length) {
                if (inText && value != null) value.append(ch, start, length);
            }

            @Override public void endElement(String uri, String localName, String qName) {
                String name = xmlName(localName, qName);
                if ("t".equals(name)) inText = false;
                else if ("si".equals(name)) {
                    output.add(value == null ? "" : value.toString());
                    inSi = false;
                }
            }
        });
    }

    private static void parseStyles(byte[] xml, Set<Integer> dateStyles) throws Exception {
        Map<Integer, String> custom = new HashMap<>();
        List<Integer> formats = new ArrayList<>();
        parseXml(xml, new DefaultHandler() {
            boolean inCellXfs;

            @Override public void startElement(String uri, String localName, String qName, Attributes attributes) {
                String name = xmlName(localName, qName);
                if ("numFmt".equals(name)) {
                    int id = parseInt(attributes.getValue("numFmtId"), -1);
                    if (id >= 0) custom.put(id, attributes.getValue("formatCode"));
                } else if ("cellXfs".equals(name)) {
                    inCellXfs = true;
                } else if (inCellXfs && "xf".equals(name)) {
                    formats.add(parseInt(attributes.getValue("numFmtId"), 0));
                }
            }

            @Override public void endElement(String uri, String localName, String qName) {
                if ("cellXfs".equals(xmlName(localName, qName))) inCellXfs = false;
            }
        });
        for (int index = 0; index < formats.size(); index++) {
            int format = formats.get(index);
            if (isDateFormat(format, custom.get(format))) dateStyles.add(index);
        }
    }

    private static List<SheetRef> parseWorkbook(Map<String, byte[]> entries, Map<String, String> actualNames) throws Exception {
        byte[] workbook = getEntry(entries, actualNames, "xl/workbook.xml");
        if (workbook == null) return new ArrayList<>();
        Map<String, String> relationships = new HashMap<>();
        byte[] rels = getEntry(entries, actualNames, "xl/_rels/workbook.xml.rels");
        if (rels != null) {
            parseXml(rels, new DefaultHandler() {
                @Override public void startElement(String uri, String localName, String qName, Attributes attributes) {
                    if ("Relationship".equals(xmlName(localName, qName))) {
                        relationships.put(attributes.getValue("Id"), attributes.getValue("Target"));
                    }
                }
            });
        }
        List<SheetRef> result = new ArrayList<>();
        parseXml(workbook, new DefaultHandler() {
            @Override public void startElement(String uri, String localName, String qName, Attributes attributes) {
                if (!"sheet".equals(xmlName(localName, qName))) return;
                String name = attributes.getValue("name");
                String rel = attributes.getValue("http://schemas.openxmlformats.org/officeDocument/2006/relationships", "id");
                if (rel == null) rel = attributes.getValue("r:id");
                String target = relationships.get(rel);
                if (target == null) return;
                String normalized = target.startsWith("/") ? target.substring(1) : normalizeZipPath("xl/" + target);
                String actual = actualNames.get(normalized.toLowerCase(Locale.ROOT));
                if (actual != null) result.add(new SheetRef(name == null ? "Лист" : name, actual));
            }
        });
        return result;
    }

    private static List<List<Object>> parseSheet(byte[] xml, List<String> sharedStrings,
                                                  Set<Integer> dateStyles) throws Exception {
        List<List<Object>> matrix = new ArrayList<>();
        parseXml(xml, new DefaultHandler() {
            TreeMap<Integer, Object> row;
            int maxColumn;
            String cellType;
            int cellStyle;
            int cellColumn;
            boolean inValue;
            boolean inInlineText;
            StringBuilder value;

            @Override public void startElement(String uri, String localName, String qName, Attributes attributes) {
                String name = xmlName(localName, qName);
                if ("row".equals(name)) {
                    row = new TreeMap<>();
                    maxColumn = -1;
                } else if ("c".equals(name) && row != null) {
                    cellType = attributes.getValue("t");
                    cellStyle = parseInt(attributes.getValue("s"), -1);
                    cellColumn = columnIndex(attributes.getValue("r"));
                    maxColumn = Math.max(maxColumn, cellColumn);
                    value = new StringBuilder();
                } else if ("v".equals(name) && value != null) {
                    inValue = true;
                } else if ("t".equals(name) && value != null && "inlineStr".equals(cellType)) {
                    inInlineText = true;
                }
            }

            @Override public void characters(char[] ch, int start, int length) {
                if ((inValue || inInlineText) && value != null) value.append(ch, start, length);
            }

            @Override public void endElement(String uri, String localName, String qName) {
                String name = xmlName(localName, qName);
                if ("v".equals(name)) inValue = false;
                else if ("t".equals(name)) inInlineText = false;
                else if ("c".equals(name) && row != null && value != null) {
                    row.put(cellColumn, decodeXlsxCell(value.toString(), cellType, cellStyle, sharedStrings, dateStyles));
                    value = null;
                } else if ("row".equals(name) && row != null) {
                    if (matrix.size() >= MAX_ROWS) throw new IllegalArgumentException("В таблице больше 200 000 строк.");
                    List<Object> values = new ArrayList<>();
                    for (int column = 0; column <= maxColumn; column++) values.add(row.get(column));
                    if (!values.isEmpty()) matrix.add(values);
                    row = null;
                }
            }
        });
        return matrix;
    }

    private static Object decodeXlsxCell(String raw, String type, int style,
                                         List<String> sharedStrings, Set<Integer> dateStyles) {
        if ("inlineStr".equals(type) || "str".equals(type)) return raw;
        if ("s".equals(type)) {
            int index = parseInt(raw, -1);
            return index >= 0 && index < sharedStrings.size() ? sharedStrings.get(index) : "";
        }
        if ("b".equals(type)) return "1".equals(raw);
        if (raw == null || raw.isEmpty()) return "";
        try {
            double number = Double.parseDouble(raw);
            if (dateStyles.contains(style)) return excelDate(number);
            long integer = (long) number;
            return number == integer ? integer : number;
        } catch (NumberFormatException ignored) {
            return raw;
        }
    }

    private static void parseXml(byte[] xml, DefaultHandler handler) throws Exception {
        SAXParserFactory factory = SAXParserFactory.newInstance();
        factory.setNamespaceAware(true);
        try { factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true); } catch (Exception ignored) {}
        try { factory.setFeature("http://xml.org/sax/features/external-general-entities", false); } catch (Exception ignored) {}
        try { factory.setFeature("http://xml.org/sax/features/external-parameter-entities", false); } catch (Exception ignored) {}
        factory.newSAXParser().parse(new InputSource(new ByteArrayInputStream(xml)), handler);
    }

    private static String xmlName(String localName, String qName) {
        if (localName != null && !localName.isEmpty()) return localName;
        int colon = qName == null ? -1 : qName.indexOf(':');
        return colon >= 0 ? qName.substring(colon + 1) : qName;
    }

    private static String normalizeZipPath(String value) {
        List<String> parts = new ArrayList<>();
        for (String part : value.replace('\\', '/').split("/")) {
            if (part.isEmpty() || ".".equals(part)) continue;
            if ("..".equals(part)) {
                if (!parts.isEmpty()) parts.remove(parts.size() - 1);
            } else parts.add(part);
        }
        return String.join("/", parts);
    }

    private static int columnIndex(String reference) {
        if (reference == null) return 0;
        int value = 0;
        for (int index = 0; index < reference.length(); index++) {
            char ch = Character.toUpperCase(reference.charAt(index));
            if (ch < 'A' || ch > 'Z') break;
            value = value * 26 + ch - 'A' + 1;
        }
        return Math.max(0, value - 1);
    }

    private static boolean hasMatrixValues(List<List<Object>> matrix) {
        for (List<Object> row : matrix) {
            for (Object value : row) if (value != null && !value.toString().trim().isEmpty()) return true;
        }
        return false;
    }

    private static boolean isDateFormat(int formatId, String code) {
        if (BUILTIN_DATE_FORMATS.contains(formatId)) return true;
        if (code == null) return false;
        String cleaned = code.replaceAll("\"[^\"]*\"|\\\\.", "");
        return DATE_FORMAT_TOKEN.matcher(cleaned).find();
    }

    private static Object excelDate(double serial) {
        long wholeDays = (long) Math.floor(serial);
        long nanos = Math.round((serial - wholeDays) * 86_400_000_000_000L);
        LocalDate date = LocalDate.of(1899, 12, 30).plusDays(wholeDays);
        if (nanos <= 0) return date;
        if (nanos >= 86_400_000_000_000L) return date.plusDays(1);
        return LocalDateTime.of(date, LocalTime.ofNanoOfDay(nanos));
    }

    private static char detectDelimiter(String text) {
        String first = text.split("\\R", 2)[0];
        char best = ';';
        int bestCount = -1;
        for (char candidate : new char[]{';', ',', '\t', '|'}) {
            int count = 0;
            for (int index = 0; index < first.length(); index++) if (first.charAt(index) == candidate) count++;
            if (count > bestCount) {
                bestCount = count;
                best = candidate;
            }
        }
        return best;
    }

    private static List<List<Object>> parseCsv(String text, char delimiter) {
        List<List<Object>> rows = new ArrayList<>();
        List<Object> row = new ArrayList<>();
        StringBuilder field = new StringBuilder();
        boolean quoted = false;
        for (int index = 0; index < text.length(); index++) {
            char ch = text.charAt(index);
            if (ch == '"') {
                if (quoted && index + 1 < text.length() && text.charAt(index + 1) == '"') {
                    field.append('"');
                    index++;
                } else quoted = !quoted;
            } else if (ch == delimiter && !quoted) {
                row.add(field.toString());
                field.setLength(0);
            } else if ((ch == '\n' || ch == '\r') && !quoted) {
                if (ch == '\r' && index + 1 < text.length() && text.charAt(index + 1) == '\n') index++;
                row.add(field.toString());
                field.setLength(0);
                rows.add(row);
                row = new ArrayList<>();
            } else field.append(ch);
        }
        if (field.length() > 0 || !row.isEmpty()) {
            row.add(field.toString());
            rows.add(row);
        }
        return rows;
    }

    private static int parseInt(String value, int fallback) {
        try { return Integer.parseInt(value); } catch (Exception ignored) { return fallback; }
    }

    private record SheetRef(String name, String path) {}

    private static final class OleFile {
        private static final int END = -2;

        private final byte[] file;
        private final int sectorSize;
        private final int miniSectorSize;
        private final int miniCutoff;
        private final int[] fat;
        private final int[] miniFat;
        private final byte[] miniStream;
        private final List<DirectoryEntry> directory;

        OleFile(byte[] file) {
            if (!isOle(file) || file.length < 512) throw new IllegalArgumentException("Некорректный файл XLS (OLE2).");
            this.file = file;
            this.sectorSize = 1 << u16(file, 30);
            this.miniSectorSize = 1 << u16(file, 32);
            this.miniCutoff = i32(file, 56);
            this.fat = readFat();
            byte[] directoryBytes = readRegularChain(i32(file, 48), file.length);
            this.directory = parseDirectory(directoryBytes);
            DirectoryEntry root = directory.stream().filter(entry -> entry.type == 5).findFirst()
                    .orElseThrow(() -> new IllegalArgumentException("В XLS отсутствует корневой OLE-каталог."));
            int miniFatStart = i32(file, 60);
            int miniFatSectors = i32(file, 64);
            byte[] miniFatBytes = miniFatStart >= 0 && miniFatSectors > 0
                    ? readRegularChain(miniFatStart, miniFatSectors * sectorSize) : new byte[0];
            this.miniFat = toIntArray(miniFatBytes);
            this.miniStream = root.startSector >= 0 && root.size > 0
                    ? readRegularChain(root.startSector, checkedSize(root.size)) : new byte[0];
        }

        byte[] readStream(String... names) {
            for (String wanted : names) {
                for (DirectoryEntry entry : directory) {
                    if (entry.type == 2 && entry.name.equalsIgnoreCase(wanted)) {
                        int size = checkedSize(entry.size);
                        return size < miniCutoff ? readMiniChain(entry.startSector, size)
                                : readRegularChain(entry.startSector, size);
                    }
                }
            }
            throw new IllegalArgumentException("В XLS не найден поток Workbook.");
        }

        private int[] readFat() {
            int fatSectorCount = i32(file, 44);
            List<Integer> fatSectors = new ArrayList<>();
            for (int index = 0; index < 109 && fatSectors.size() < fatSectorCount; index++) {
                int sector = i32(file, 76 + index * 4);
                if (sector >= 0) fatSectors.add(sector);
            }
            int difatSector = i32(file, 68);
            int difatCount = i32(file, 72);
            for (int chain = 0; chain < difatCount && difatSector >= 0 && fatSectors.size() < fatSectorCount; chain++) {
                int offset = sectorOffset(difatSector);
                int entries = sectorSize / 4 - 1;
                for (int index = 0; index < entries && fatSectors.size() < fatSectorCount; index++) {
                    int sector = i32(file, offset + index * 4);
                    if (sector >= 0) fatSectors.add(sector);
                }
                difatSector = i32(file, offset + entries * 4);
            }
            int[] result = new int[fatSectors.size() * sectorSize / 4];
            int out = 0;
            for (int sector : fatSectors) {
                int offset = sectorOffset(sector);
                for (int index = 0; index < sectorSize / 4; index++) result[out++] = i32(file, offset + index * 4);
            }
            return result;
        }

        private byte[] readRegularChain(int startSector, int requestedSize) {
            if (startSector < 0 || requestedSize <= 0) return new byte[0];
            ByteArrayOutputStream out = new ByteArrayOutputStream(Math.min(requestedSize, file.length));
            int sector = startSector;
            int visited = 0;
            while (sector >= 0 && sector != END && out.size() < requestedSize) {
                if (sector >= fat.length || visited++ > fat.length) throw new IllegalArgumentException("Повреждена цепочка секторов XLS.");
                int offset = sectorOffset(sector);
                int count = Math.min(sectorSize, Math.min(requestedSize - out.size(), file.length - offset));
                if (count <= 0) throw new IllegalArgumentException("Сектор XLS выходит за границы файла.");
                out.write(file, offset, count);
                sector = fat[sector];
            }
            return out.toByteArray();
        }

        private byte[] readMiniChain(int startSector, int requestedSize) {
            if (startSector < 0 || requestedSize <= 0) return new byte[0];
            ByteArrayOutputStream out = new ByteArrayOutputStream(requestedSize);
            int sector = startSector;
            int visited = 0;
            while (sector >= 0 && sector != END && out.size() < requestedSize) {
                if (sector >= miniFat.length || visited++ > miniFat.length) throw new IllegalArgumentException("Повреждена miniFAT-цепочка XLS.");
                int offset = sector * miniSectorSize;
                int count = Math.min(miniSectorSize, Math.min(requestedSize - out.size(), miniStream.length - offset));
                if (count <= 0) throw new IllegalArgumentException("Mini-сектор XLS выходит за границы файла.");
                out.write(miniStream, offset, count);
                sector = miniFat[sector];
            }
            return out.toByteArray();
        }

        private List<DirectoryEntry> parseDirectory(byte[] data) {
            List<DirectoryEntry> entries = new ArrayList<>();
            for (int offset = 0; offset + 128 <= data.length; offset += 128) {
                int nameBytes = u16(data, offset + 64);
                int type = data[offset + 66] & 0xff;
                if (nameBytes < 2 || type == 0) continue;
                int length = Math.min(nameBytes - 2, 64);
                String name = new String(data, offset, length, StandardCharsets.UTF_16LE);
                int start = i32(data, offset + 116);
                long size = Integer.toUnsignedLong(i32(data, offset + 120));
                if (u16(file, 26) >= 4) size |= Integer.toUnsignedLong(i32(data, offset + 124)) << 32;
                entries.add(new DirectoryEntry(name, type, start, size));
            }
            return entries;
        }

        private int sectorOffset(int sector) {
            long offset = (long) (sector + 1) * sectorSize;
            if (sector < 0 || offset < 0 || offset + sectorSize > file.length) {
                throw new IllegalArgumentException("Некорректный номер сектора XLS: " + sector);
            }
            return (int) offset;
        }

        private int checkedSize(long size) {
            if (size < 0 || size > MAX_INPUT_BYTES) throw new IllegalArgumentException("Поток XLS слишком велик.");
            return (int) size;
        }

        private int[] toIntArray(byte[] bytes) {
            int[] result = new int[bytes.length / 4];
            for (int index = 0; index < result.length; index++) result[index] = i32(bytes, index * 4);
            return result;
        }

        private record DirectoryEntry(String name, int type, int startSector, long size) {}
    }

    private static final class BiffWorkbook {
        private final byte[] data;
        private final List<String> sharedStrings = new ArrayList<>();
        private final List<Integer> xfFormats = new ArrayList<>();
        private final Map<Integer, String> customFormats = new HashMap<>();
        private final List<BoundSheet> sheets = new ArrayList<>();

        BiffWorkbook(byte[] data) {
            this.data = data;
            parseGlobals();
        }

        TableData readFirstTable(String sourceName) {
            for (BoundSheet sheet : sheets) {
                List<List<Object>> matrix = parseSheet(sheet.offset);
                if (hasMatrixValues(matrix)) return TableData.fromMatrix(sourceName, sheet.name, matrix);
            }
            throw new IllegalArgumentException("В XLS не найден непустой лист с таблицей.");
        }

        private void parseGlobals() {
            int position = 0;
            while (position + 4 <= data.length) {
                int sid = u16(data, position);
                int length = u16(data, position + 2);
                int payload = position + 4;
                if (payload + length > data.length) break;
                if (sid == 0x0085 && length >= 8) {
                    int offset = i32(data, payload);
                    int nameLength = data[payload + 6] & 0xff;
                    int flags = data[payload + 7] & 0xff;
                    String name = readBiffChars(data, payload + 8, nameLength, (flags & 1) != 0);
                    sheets.add(new BoundSheet(offset, name));
                } else if (sid == 0x00E0 && length >= 4) {
                    xfFormats.add(u16(data, payload + 2));
                } else if (sid == 0x041E && length >= 5) {
                    int formatId = u16(data, payload);
                    int chars = u16(data, payload + 2);
                    int flags = data[payload + 4] & 0xff;
                    customFormats.put(formatId, readBiffChars(data, payload + 5, chars, (flags & 1) != 0));
                } else if (sid == 0x00FC && length >= 8) {
                    List<byte[]> segments = new ArrayList<>();
                    segments.add(Arrays.copyOfRange(data, payload, payload + length));
                    int next = payload + length;
                    while (next + 4 <= data.length && u16(data, next) == 0x003C) {
                        int continuationLength = u16(data, next + 2);
                        if (next + 4 + continuationLength > data.length) break;
                        segments.add(Arrays.copyOfRange(data, next + 4, next + 4 + continuationLength));
                        next += 4 + continuationLength;
                    }
                    parseSst(segments);
                    position = next;
                    continue;
                } else if (sid == 0x000A && !sheets.isEmpty()) {
                    break;
                }
                position = payload + length;
            }
            if (sheets.isEmpty()) throw new IllegalArgumentException("В XLS отсутствует описание листов.");
        }

        private void parseSst(List<byte[]> segments) {
            SegmentCursor cursor = new SegmentCursor(segments);
            cursor.readU32();
            int unique = cursor.readU32();
            for (int index = 0; index < unique && cursor.hasData(); index++) {
                int chars = cursor.readU16();
                int flags = cursor.readU8();
                int richRuns = (flags & 0x08) != 0 ? cursor.readU16() : 0;
                int extensionBytes = (flags & 0x04) != 0 ? cursor.readU32() : 0;
                String text = cursor.readCharacters(chars, (flags & 1) != 0);
                cursor.skip(richRuns * 4 + extensionBytes);
                sharedStrings.add(text);
            }
        }

        private List<List<Object>> parseSheet(int start) {
            TreeMap<Integer, TreeMap<Integer, Object>> rows = new TreeMap<>();
            int position = Math.max(0, start);
            while (position + 4 <= data.length) {
                int sid = u16(data, position);
                int length = u16(data, position + 2);
                int payload = position + 4;
                if (payload + length > data.length) break;
                if (sid == 0x000A) break;
                if (length >= 6) {
                    int row = u16(data, payload);
                    int col = u16(data, payload + 2);
                    int xf = u16(data, payload + 4);
                    Object value = null;
                    if (sid == 0x00FD && length >= 10) {
                        int index = i32(data, payload + 6);
                        value = index >= 0 && index < sharedStrings.size() ? sharedStrings.get(index) : "";
                    } else if (sid == 0x0203 && length >= 14) {
                        value = numericOrDate(f64(data, payload + 6), xf);
                    } else if (sid == 0x027E && length >= 10) {
                        value = numericOrDate(decodeRk(i32(data, payload + 6)), xf);
                    } else if (sid == 0x00BD && length >= 12) {
                        int lastCol = u16(data, payload + length - 2);
                        int offset = payload + 4;
                        for (int currentCol = col; currentCol <= lastCol && offset + 6 <= payload + length - 2; currentCol++) {
                            int currentXf = u16(data, offset);
                            Object current = numericOrDate(decodeRk(i32(data, offset + 2)), currentXf);
                            rows.computeIfAbsent(row, ignored -> new TreeMap<>()).put(currentCol, current);
                            offset += 6;
                        }
                    } else if (sid == 0x0204 && length >= 8) {
                        int chars = u16(data, payload + 6);
                        value = new String(data, payload + 8, Math.min(chars, length - 8), Charset.forName("windows-1251"));
                    } else if (sid == 0x0006 && length >= 14 && (data[payload + 12] & 0xff) != 0xff) {
                        value = numericOrDate(f64(data, payload + 6), xf);
                    }
                    if (value != null) rows.computeIfAbsent(row, ignored -> new TreeMap<>()).put(col, value);
                }
                position = payload + length;
            }
            List<List<Object>> matrix = new ArrayList<>();
            for (TreeMap<Integer, Object> values : rows.values()) {
                if (matrix.size() >= MAX_ROWS) throw new IllegalArgumentException("В таблице больше 200 000 строк.");
                int max = values.isEmpty() ? -1 : values.lastKey();
                List<Object> row = new ArrayList<>();
                for (int column = 0; column <= max; column++) row.add(values.get(column));
                matrix.add(row);
            }
            return matrix;
        }

        private Object numericOrDate(double value, int xfIndex) {
            int format = xfIndex >= 0 && xfIndex < xfFormats.size() ? xfFormats.get(xfIndex) : -1;
            if (isDateFormat(format, customFormats.get(format))) return excelDate(value);
            long integer = (long) value;
            return value == integer ? integer : value;
        }

        private static double decodeRk(int raw) {
            boolean divide = (raw & 1) != 0;
            double value;
            if ((raw & 2) != 0) value = raw >> 2;
            else value = Double.longBitsToDouble(Integer.toUnsignedLong(raw & 0xFFFFFFFC) << 32);
            return divide ? value / 100.0 : value;
        }

        private record BoundSheet(int offset, String name) {}
    }

    private static final class SegmentCursor {
        private final List<byte[]> segments;
        private int segmentIndex;
        private int offset;

        SegmentCursor(List<byte[]> segments) { this.segments = segments; }

        boolean hasData() {
            advance();
            return segmentIndex < segments.size();
        }

        int readU8() {
            advance();
            if (segmentIndex >= segments.size()) throw new IllegalArgumentException("Оборвана таблица строк XLS.");
            return segments.get(segmentIndex)[offset++] & 0xff;
        }

        int readU16() { return readU8() | readU8() << 8; }

        int readU32() { return readU8() | readU8() << 8 | readU8() << 16 | readU8() << 24; }

        String readCharacters(int count, boolean wide) {
            StringBuilder text = new StringBuilder(count);
            for (int index = 0; index < count; index++) {
                if (remaining() < (wide ? 2 : 1)) {
                    nextSegment();
                    wide = (readU8() & 1) != 0;
                }
                int character = readU8();
                if (wide) character |= readU8() << 8;
                text.append((char) character);
            }
            return text.toString();
        }

        void skip(int count) { for (int index = 0; index < count; index++) readU8(); }

        private int remaining() {
            return segmentIndex < segments.size() ? segments.get(segmentIndex).length - offset : 0;
        }

        private void advance() {
            while (segmentIndex < segments.size() && offset >= segments.get(segmentIndex).length) nextSegment();
        }

        private void nextSegment() {
            segmentIndex++;
            offset = 0;
        }
    }

    private static String readBiffChars(byte[] data, int offset, int count, boolean wide) {
        int bytes = Math.min(data.length - offset, count * (wide ? 2 : 1));
        if (bytes <= 0) return "";
        return new String(data, offset, bytes, wide ? StandardCharsets.UTF_16LE : Charset.forName("windows-1251"));
    }

    private static int u16(byte[] data, int offset) {
        if (offset < 0 || offset + 2 > data.length) throw new IllegalArgumentException("Повреждены данные XLS.");
        return (data[offset] & 0xff) | (data[offset + 1] & 0xff) << 8;
    }

    private static int i32(byte[] data, int offset) {
        if (offset < 0 || offset + 4 > data.length) throw new IllegalArgumentException("Повреждены данные XLS.");
        return (data[offset] & 0xff) | (data[offset + 1] & 0xff) << 8
                | (data[offset + 2] & 0xff) << 16 | data[offset + 3] << 24;
    }

    private static double f64(byte[] data, int offset) {
        if (offset < 0 || offset + 8 > data.length) throw new IllegalArgumentException("Повреждены данные XLS.");
        return ByteBuffer.wrap(data, offset, 8).order(ByteOrder.LITTLE_ENDIAN).getDouble();
    }
}
