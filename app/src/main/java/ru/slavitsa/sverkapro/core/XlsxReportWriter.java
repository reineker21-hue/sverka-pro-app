package ru.slavitsa.sverkapro.core;

import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

public final class XlsxReportWriter {
    private XlsxReportWriter() {}

    public static void write(ReconciliationEngine.Result result, OutputStream output) throws IOException {
        List<Sheet> sheets = buildSheets(result);
        try (ZipOutputStream zip = new ZipOutputStream(output)) {
            put(zip, "[Content_Types].xml", contentTypes(sheets.size()));
            put(zip, "_rels/.rels", rootRelationships());
            put(zip, "docProps/app.xml", appProperties(sheets));
            put(zip, "docProps/core.xml", coreProperties());
            put(zip, "xl/workbook.xml", workbook(sheets));
            put(zip, "xl/_rels/workbook.xml.rels", workbookRelationships(sheets.size()));
            put(zip, "xl/styles.xml", styles());
            for (int index = 0; index < sheets.size(); index++) {
                put(zip, "xl/worksheets/sheet" + (index + 1) + ".xml", sheetXml(sheets.get(index)));
            }
        }
    }

    private static List<Sheet> buildSheets(ReconciliationEngine.Result result) {
        List<Sheet> sheets = new ArrayList<>();
        List<List<Object>> summary = new ArrayList<>();
        summary.add(List.of("СВЕРКА ПРО — ИТОГ", ""));
        summary.add(List.of("Версия приложения", "2.0.3 — нативный Android"));
        summary.add(List.of("Акт 1", result.first().sourceName));
        summary.add(List.of("Акт 2", result.second().sourceName));
        summary.add(List.of("Строк в акте 1", result.first().rows.size()));
        summary.add(List.of("Строк в акте 2", result.second().rows.size()));
        summary.add(List.of("Отдельных расхождений", result.differences().size()));
        summary.add(List.of("Только в акте 1", result.onlyFirst().size()));
        summary.add(List.of("Только в акте 2", result.onlySecond().size()));
        summary.add(List.of("Совпадений", result.matches().size()));
        summary.add(List.of("Начальное сальдо — разница", nullable(result.openingDifference())));
        summary.add(List.of("Начисления — разница", result.accrualDifference()));
        summary.add(List.of("Оплаты — разница", result.settlementDifference()));
        summary.add(List.of("Конечное сальдо — разница", nullable(result.endingDifference())));
        sheets.add(new Sheet("ИТОГ", summary, true));

        List<List<Object>> differences = new ArrayList<>();
        differences.add(List.of("Ключ", "Поле", "Акт 1", "Акт 2", "Разница", "Статус", "Рекомендация"));
        for (ReconciliationEngine.Difference item : result.differences()) {
            differences.add(List.of(item.key(), item.field(), safe(item.valueFirst()), safe(item.valueSecond()),
                    safe(item.delta()), item.status(), item.recommendation()));
        }
        sheets.add(new Sheet("РАЗЛИЧИЯ", differences, true));
        sheets.add(rowsSheet("ТОЛЬКО АКТ 1", result.onlyFirst()));
        sheets.add(rowsSheet("ТОЛЬКО АКТ 2", result.onlySecond()));

        List<List<Object>> matches = new ArrayList<>();
        matches.add(List.of("Ключ", "Статус"));
        for (ReconciliationEngine.Match item : result.matches()) matches.add(List.of(item.key(), item.status()));
        sheets.add(new Sheet("СОВПАДЕНИЯ", matches, true));
        return sheets;
    }

    private static Sheet rowsSheet(String name, List<Map<String, Object>> rows) {
        if (rows.isEmpty()) return new Sheet(name, List.of(List.of("Нет данных")), true);
        LinkedHashSet<String> headers = new LinkedHashSet<>();
        for (Map<String, Object> row : rows) headers.addAll(row.keySet());
        List<List<Object>> values = new ArrayList<>();
        values.add(new ArrayList<>(headers));
        for (Map<String, Object> row : rows) {
            List<Object> line = new ArrayList<>();
            for (String header : headers) line.add(safe(row.get(header)));
            values.add(line);
        }
        return new Sheet(name, values, true);
    }

    private static Object nullable(double value) { return Double.isNaN(value) ? "—" : value; }
    private static Object safe(Object value) { return value == null ? "" : value; }

    private static String sheetXml(Sheet sheet) {
        StringBuilder xml = new StringBuilder(32_768);
        int rows = Math.max(1, sheet.rows.size());
        int columns = Math.max(1, maxColumns(sheet.rows));
        String range = "A1:" + cellReference(columns - 1, rows);
        xml.append("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>")
                .append("<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">")
                .append("<dimension ref=\"").append(range).append("\"/>")
                .append("<sheetViews><sheetView workbookViewId=\"0\"><pane ySplit=\"1\" topLeftCell=\"A2\" activePane=\"bottomLeft\" state=\"frozen\"/></sheetView></sheetViews>")
                .append("<sheetFormatPr defaultRowHeight=\"18\"/><sheetData>");
        for (int rowIndex = 0; rowIndex < sheet.rows.size(); rowIndex++) {
            List<Object> row = sheet.rows.get(rowIndex);
            xml.append("<row r=\"").append(rowIndex + 1).append("\">");
            for (int column = 0; column < row.size(); column++) {
                Object value = row.get(column);
                int style = rowIndex == 0 && sheet.header ? 1 : value instanceof Number ? 2 : 0;
                appendCell(xml, cellReference(column, rowIndex + 1), value, style);
            }
            xml.append("</row>");
        }
        xml.append("</sheetData><autoFilter ref=\"").append(range).append("\"/></worksheet>");
        return xml.toString();
    }

    private static void appendCell(StringBuilder xml, String reference, Object value, int style) {
        if (value instanceof Number number && Double.isFinite(number.doubleValue())) {
            xml.append("<c r=\"").append(reference).append("\" s=\"").append(style).append("\"><v>")
                    .append(number.toString()).append("</v></c>");
            return;
        }
        String text = value == null ? "" : value.toString();
        if (text.length() > 32_767) text = text.substring(0, 32_767);
        xml.append("<c r=\"").append(reference).append("\" t=\"inlineStr\" s=\"").append(style)
                .append("\"><is><t xml:space=\"preserve\">").append(escape(text)).append("</t></is></c>");
    }

    private static int maxColumns(Collection<List<Object>> rows) {
        int max = 1;
        for (List<Object> row : rows) max = Math.max(max, row.size());
        return max;
    }

    private static String cellReference(int column, int row) {
        StringBuilder letters = new StringBuilder();
        int value = column + 1;
        while (value > 0) {
            value--;
            letters.insert(0, (char) ('A' + value % 26));
            value /= 26;
        }
        return letters + Integer.toString(row);
    }

    private static String contentTypes(int sheetCount) {
        StringBuilder xml = new StringBuilder("<?xml version=\"1.0\" encoding=\"UTF-8\"?>")
                .append("<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">")
                .append("<Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>")
                .append("<Default Extension=\"xml\" ContentType=\"application/xml\"/>")
                .append("<Override PartName=\"/xl/workbook.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml\"/>")
                .append("<Override PartName=\"/xl/styles.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml\"/>")
                .append("<Override PartName=\"/docProps/core.xml\" ContentType=\"application/vnd.openxmlformats-package.core-properties+xml\"/>")
                .append("<Override PartName=\"/docProps/app.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.extended-properties+xml\"/>");
        for (int index = 1; index <= sheetCount; index++) {
            xml.append("<Override PartName=\"/xl/worksheets/sheet").append(index)
                    .append(".xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml\"/>");
        }
        return xml.append("</Types>").toString();
    }

    private static String rootRelationships() {
        return "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
                + "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
                + "<Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"xl/workbook.xml\"/>"
                + "<Relationship Id=\"rId2\" Type=\"http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties\" Target=\"docProps/core.xml\"/>"
                + "<Relationship Id=\"rId3\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties\" Target=\"docProps/app.xml\"/>"
                + "</Relationships>";
    }

    private static String workbook(List<Sheet> sheets) {
        StringBuilder xml = new StringBuilder("<?xml version=\"1.0\" encoding=\"UTF-8\"?>")
                .append("<workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\"><sheets>");
        for (int index = 0; index < sheets.size(); index++) {
            xml.append("<sheet name=\"").append(escapeAttribute(sheets.get(index).name)).append("\" sheetId=\"")
                    .append(index + 1).append("\" r:id=\"rId").append(index + 1).append("\"/>");
        }
        return xml.append("</sheets></workbook>").toString();
    }

    private static String workbookRelationships(int sheetCount) {
        StringBuilder xml = new StringBuilder("<?xml version=\"1.0\" encoding=\"UTF-8\"?>")
                .append("<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">");
        for (int index = 1; index <= sheetCount; index++) {
            xml.append("<Relationship Id=\"rId").append(index)
                    .append("\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet\" Target=\"worksheets/sheet")
                    .append(index).append(".xml\"/>");
        }
        xml.append("<Relationship Id=\"rId").append(sheetCount + 1)
                .append("\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles\" Target=\"styles.xml\"/>")
                .append("</Relationships>");
        return xml.toString();
    }

    private static String styles() {
        return "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
                + "<styleSheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">"
                + "<fonts count=\"2\"><font><sz val=\"11\"/><name val=\"Calibri\"/></font><font><b/><color rgb=\"FFFFFFFF\"/><sz val=\"11\"/><name val=\"Calibri\"/></font></fonts>"
                + "<fills count=\"3\"><fill><patternFill patternType=\"none\"/></fill><fill><patternFill patternType=\"gray125\"/></fill><fill><patternFill patternType=\"solid\"><fgColor rgb=\"FF107C41\"/><bgColor indexed=\"64\"/></patternFill></fill></fills>"
                + "<borders count=\"1\"><border><left/><right/><top/><bottom/><diagonal/></border></borders>"
                + "<cellStyleXfs count=\"1\"><xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"0\"/></cellStyleXfs>"
                + "<cellXfs count=\"3\"><xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"0\" xfId=\"0\"/>"
                + "<xf numFmtId=\"0\" fontId=\"1\" fillId=\"2\" borderId=\"0\" xfId=\"0\" applyFont=\"1\" applyFill=\"1\"/>"
                + "<xf numFmtId=\"4\" fontId=\"0\" fillId=\"0\" borderId=\"0\" xfId=\"0\" applyNumberFormat=\"1\"/></cellXfs>"
                + "<cellStyles count=\"1\"><cellStyle name=\"Обычный\" xfId=\"0\" builtinId=\"0\"/></cellStyles>"
                + "</styleSheet>";
    }

    private static String appProperties(List<Sheet> sheets) {
        StringBuilder titles = new StringBuilder();
        for (Sheet sheet : sheets) titles.append("<vt:lpstr>").append(escape(sheet.name)).append("</vt:lpstr>");
        return "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
                + "<Properties xmlns=\"http://schemas.openxmlformats.org/officeDocument/2006/extended-properties\" xmlns:vt=\"http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes\">"
                + "<Application>Сверка ПРО 2.0.3</Application><TitlesOfParts><vt:vector size=\"" + sheets.size()
                + "\" baseType=\"lpstr\">" + titles + "</vt:vector></TitlesOfParts></Properties>";
    }

    private static String coreProperties() {
        String now = DateTimeFormatter.ISO_INSTANT.format(Instant.now().atOffset(ZoneOffset.UTC));
        return "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
                + "<cp:coreProperties xmlns:cp=\"http://schemas.openxmlformats.org/package/2006/metadata/core-properties\" xmlns:dc=\"http://purl.org/dc/elements/1.1/\" xmlns:dcterms=\"http://purl.org/dc/terms/\" xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\">"
                + "<dc:creator>Сверка ПРО</dc:creator><cp:lastModifiedBy>Сверка ПРО</cp:lastModifiedBy>"
                + "<dcterms:created xsi:type=\"dcterms:W3CDTF\">" + now + "</dcterms:created>"
                + "<dcterms:modified xsi:type=\"dcterms:W3CDTF\">" + now + "</dcterms:modified></cp:coreProperties>";
    }

    private static void put(ZipOutputStream zip, String name, String content) throws IOException {
        zip.putNextEntry(new ZipEntry(name));
        zip.write(content.getBytes(StandardCharsets.UTF_8));
        zip.closeEntry();
    }

    private static String escape(Object value) {
        return value == null ? "" : value.toString().replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;");
    }

    private static String escapeAttribute(Object value) {
        return escape(value).replace("\"", "&quot;").replace("'", "&apos;");
    }

    private record Sheet(String name, List<List<Object>> rows, boolean header) {}
}
