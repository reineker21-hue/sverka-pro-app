package ru.slavitsa.sverkapro;

import ru.slavitsa.sverkapro.core.SpreadsheetReader;
import ru.slavitsa.sverkapro.core.TableData;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.time.Instant;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.List;

import jxl.Cell;
import jxl.DateCell;
import jxl.NumberCell;
import jxl.Sheet;
import jxl.Workbook;
import jxl.WorkbookSettings;
import jxl.biff.StringHelper;
import jxl.write.Label;
import jxl.write.WritableSheet;
import jxl.write.WritableWorkbook;

final class AndroidSpreadsheetReader {
    private static final int MAX_INPUT_BYTES = 32 * 1024 * 1024;
    private static final byte[] OLE_SIGNATURE = {
            (byte) 0xD0, (byte) 0xCF, 0x11, (byte) 0xE0,
            (byte) 0xA1, (byte) 0xB1, 0x1A, (byte) 0xE1};

    static {
        // JExcelAPI defaults to the obsolete alias "UnicodeLittle". On Android
        // it corrupts some BIFF8 shared strings with U+FFFD replacement signs.
        StringHelper.UNICODE_ENCODING = "UTF-16LE";
    }

    private AndroidSpreadsheetReader() {}

    static TableData read(InputStream input, String sourceName) throws Exception {
        byte[] data = readLimited(input);
        if (!isOle(data)) return SpreadsheetReader.read(new ByteArrayInputStream(data), sourceName);

        TableData nativeTable = null;
        Throwable nativeError = null;
        try {
            nativeTable = SpreadsheetReader.read(new ByteArrayInputStream(data), sourceName);
        } catch (Exception | LinkageError error) {
            nativeError = error;
        }

        try {
            TableData jexcelTable = readLegacyXls(data, sourceName);
            if (nativeTable != null && nativeTable.rows.size() == jexcelTable.rows.size()) {
                TableData merged = mergeTextAndNumbers(nativeTable, jexcelTable);
                CrashLogger.breadcrumb("xls:reader=merged rows=" + merged.rows.size());
                return merged;
            }
            CrashLogger.breadcrumb("xls:reader=jexcel rows=" + jexcelTable.rows.size());
            return jexcelTable;
        } catch (Exception | LinkageError jexcelError) {
            if (nativeTable != null) {
                CrashLogger.breadcrumb("xls:reader=native rows=" + nativeTable.rows.size());
                return nativeTable;
            }
            if (nativeError != null) jexcelError.addSuppressed(nativeError);
            if (jexcelError instanceof Exception exception) throw exception;
            throw (LinkageError) jexcelError;
        }
    }

    static TableData createAndReadSelfTestXls() throws Exception {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        WritableWorkbook workbook = Workbook.createWorkbook(output);
        try {
            WritableSheet sheet = workbook.createSheet("Лист1", 0);
            sheet.addCell(new Label(0, 0, "Дата"));
            sheet.addCell(new Label(1, 0, "Документ"));
            sheet.addCell(new Label(2, 0, "Дебет"));
            sheet.addCell(new Label(3, 0, "Кредит"));
            sheet.addCell(new Label(0, 1, "01.07.26"));
            sheet.addCell(new Label(1, 1, "Поступление № ТЕСТ-1 от 01.07.2026"));
            sheet.addCell(new jxl.write.Number(2, 1, 1250.75));
            sheet.addCell(new Label(0, 2, "02.07.26"));
            sheet.addCell(new Label(1, 2, "Оплата № ТЕСТ-2 от 02.07.2026"));
            sheet.addCell(new jxl.write.Number(3, 2, 500.25));
            workbook.write();
        } finally {
            workbook.close();
        }
        return read(new ByteArrayInputStream(output.toByteArray()), "android-selftest.xls");
    }

    private static TableData readLegacyXls(byte[] data, String sourceName) throws Exception {
        WorkbookSettings settings = new WorkbookSettings();
        settings.setSuppressWarnings(true);
        settings.setGCDisabled(true);
        Workbook workbook = Workbook.getWorkbook(new ByteArrayInputStream(data), settings);
        try {
            IllegalArgumentException lastError = null;
            for (Sheet sheet : workbook.getSheets()) {
                List<List<Object>> matrix = new ArrayList<>(sheet.getRows());
                for (int row = 0; row < sheet.getRows(); row++) {
                    List<Object> values = new ArrayList<>(sheet.getColumns());
                    for (int column = 0; column < sheet.getColumns(); column++) {
                        values.add(cellValue(sheet.getCell(column, row)));
                    }
                    matrix.add(values);
                }
                try {
                    return TableData.fromMatrix(sourceName, sheet.getName(), matrix);
                } catch (IllegalArgumentException error) {
                    lastError = error;
                }
            }
            if (lastError != null) throw lastError;
            throw new IllegalArgumentException("В XLS не найден непустой лист с таблицей.");
        } finally {
            workbook.close();
        }
    }

    private static TableData mergeTextAndNumbers(TableData textTable, TableData numberTable) {
        List<List<Object>> matrix = new ArrayList<>(textTable.rows.size() + 1);
        matrix.add(new ArrayList<>(textTable.headers));
        int columns = textTable.headers.size();
        for (int rowIndex = 0; rowIndex < textTable.rows.size(); rowIndex++) {
            List<Object> row = new ArrayList<>(columns);
            for (int columnIndex = 0; columnIndex < columns; columnIndex++) {
                String textHeader = textTable.headers.get(columnIndex);
                Object value = textTable.rows.get(rowIndex).get(textHeader);
                if (columnIndex < numberTable.headers.size()) {
                    String numberHeader = numberTable.headers.get(columnIndex);
                    Object numericValue = numberTable.rows.get(rowIndex).get(numberHeader);
                    if (numericValue instanceof Number) value = numericValue;
                }
                row.add(value);
            }
            matrix.add(row);
        }
        return TableData.fromMatrix(textTable.sourceName, textTable.sheetName, matrix);
    }

    private static Object cellValue(Cell cell) {
        if (cell instanceof DateCell dateCell) {
            return Instant.ofEpochMilli(dateCell.getDate().getTime())
                    .atZone(ZoneId.systemDefault()).toLocalDate();
        }
        if (cell instanceof NumberCell numberCell) {
            double value = numberCell.getValue();
            long integer = (long) value;
            return value == integer ? integer : value;
        }
        String value = cell.getContents();
        return value == null || value.isEmpty() ? null : value;
    }

    private static byte[] readLimited(InputStream input) throws IOException {
        try (InputStream in = input; ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[64 * 1024];
            int total = 0;
            int count;
            while ((count = in.read(buffer)) >= 0) {
                total += count;
                if (total > MAX_INPUT_BYTES) throw new IOException("Файл превышает допустимый размер 32 МБ.");
                out.write(buffer, 0, count);
            }
            return out.toByteArray();
        }
    }

    private static boolean isOle(byte[] data) {
        if (data.length < OLE_SIGNATURE.length) return false;
        for (int index = 0; index < OLE_SIGNATURE.length; index++) {
            if (data[index] != OLE_SIGNATURE[index]) return false;
        }
        return true;
    }
}
