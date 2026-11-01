-- MySQL dump 10.13  Distrib 8.0.46, for Win64 (x86_64)
--
-- Host: 127.0.0.1    Database: smartprint
-- ------------------------------------------------------
-- Server version	8.0.46

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `orders`
--

DROP TABLE IF EXISTS `orders`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `orders` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `file_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `copies` int NOT NULL DEFAULT '1',
  `color_mode` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'bw',
  `duplex` tinyint(1) NOT NULL DEFAULT '0',
  `page_range` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'all',
  `selected_page_count` int NOT NULL,
  `physical_sheet_count` int NOT NULL,
  `price_per_page` decimal(10,2) NOT NULL,
  `total_amount` decimal(10,2) NOT NULL,
  `currency` varchar(10) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'INR',
  `status` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'OPTIONS_SELECTED',
  `created_at` datetime NOT NULL DEFAULT (now()),
  `updated_at` datetime NOT NULL DEFAULT (now()),
  `order_number` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_orders_order_number` (`order_number`),
  KEY `ix_orders_file_id` (`file_id`),
  CONSTRAINT `fk_orders_files_id` FOREIGN KEY (`file_id`) REFERENCES `files` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `orders`
--

LOCK TABLES `orders` WRITE;
/*!40000 ALTER TABLE `orders` DISABLE KEYS */;
INSERT INTO `orders` VALUES ('0beec245-ca8e-426e-b865-34a0ae117836','8b178e4f-2561-4226-af92-56338c3a2fb7',1,'bw',0,'all',12,12,3.00,36.00,'INR','CREATED','2026-10-24 07:07:59','2026-10-24 07:07:59','SP-000011'),('1ad4287e-8d56-46d7-a108-fd48143aca23','48999d1b-e0a5-4ff1-ab9d-838ad8207974',1,'bw',0,'all',5,5,2.00,10.00,'INR','OPTIONS_SELECTED','2026-09-06 18:27:42','2026-09-06 18:27:42','SP-000009'),('742ae281-c11f-4995-9fe4-7271be06b51b','104623a2-3d39-48f5-875e-4bcee00ffc1b',1,'bw',0,'all',3,3,2.00,6.00,'INR','OPTIONS_SELECTED','2026-09-13 07:25:25','2026-09-13 07:25:25','SP-000010'),('a2080e35-a25a-49c7-ae1d-b7dbdf0271d0','e1920910-bfda-460d-a193-a856e191f7a2',1,'bw',0,'all',1,1,2.00,2.00,'INR','OPTIONS_SELECTED','2026-09-05 19:14:53','2026-09-05 19:14:53','SP-000004'),('a5250a3f-5798-4193-8a73-68da0de4c19c','a6a22055-eeb5-4165-9d69-a4ad92e88465',1,'bw',0,'all',1,1,2.00,2.00,'INR','OPTIONS_SELECTED','2026-09-06 18:22:56','2026-09-06 18:22:56','SP-000007'),('a8b24790-430e-4385-aadb-de43b96747e8','4beb72dc-62f7-4414-9c9a-db9e4fcd43fd',1,'bw',0,'all',1,1,2.00,2.00,'INR','OPTIONS_SELECTED','2026-09-06 15:10:36','2026-09-06 15:10:36','SP-000005'),('b13b6279-7370-4ff1-bedd-cdd73fe7ec4b','c13cc567-4c23-4b02-9f6e-dcdbd684a350',5,'bw',0,'all',12,60,3.00,180.00,'INR','CREATED','2026-10-24 07:09:10','2026-10-24 07:09:10','SP-000012'),('bd372e25-8523-4461-9194-d038127b6d24','66a88898-4b39-47fa-8b27-be57e17d6fe9',1,'bw',0,'all',1,1,2.00,2.00,'INR','OPTIONS_SELECTED','2026-09-05 19:06:47','2026-09-05 19:06:47','SP-000003'),('c7518c1f-00e4-46a1-b6f0-1003b13d738c','b66f6d47-1249-4b13-804c-b6a69b06840d',1,'color',0,'all',1,1,5.00,5.00,'INR','OPTIONS_SELECTED','2026-09-06 18:21:59','2026-09-06 18:21:59','SP-000006'),('de7d6656-9739-4771-abf4-66ff217b70c8','66a88898-4b39-47fa-8b27-be57e17d6fe9',4,'color',1,'all',1,4,5.00,20.00,'INR','OPTIONS_SELECTED','2026-09-05 19:00:50','2026-09-05 19:00:50','SP-000002'),('e1f45160-793e-45cd-9f6c-ad08f3bd45f8','8a785222-92e5-4211-9137-ef854e4716e2',2,'bw',0,'all',1,2,2.00,4.00,'INR','OPTIONS_SELECTED','2026-09-05 18:59:27','2026-09-05 18:59:27','SP-000001'),('f775a120-e562-4b4a-8374-d4a81c5040b3','08f70b5b-25e3-41a1-9ac7-a05e64329177',1,'bw',0,'all',1,1,2.00,2.00,'INR','OPTIONS_SELECTED','2026-09-06 18:25:13','2026-09-06 18:25:13','SP-000008');
/*!40000 ALTER TABLE `orders` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-10-24 13:34:15
