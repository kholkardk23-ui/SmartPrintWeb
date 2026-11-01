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
-- Table structure for table `files`
--

DROP TABLE IF EXISTS `files`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `files` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `original_filename` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `stored_filename` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `file_size` int NOT NULL,
  `page_count` int NOT NULL,
  `status` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `stored_filename` (`stored_filename`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `files`
--

LOCK TABLES `files` WRITE;
/*!40000 ALTER TABLE `files` DISABLE KEYS */;
INSERT INTO `files` VALUES ('08f70b5b-25e3-41a1-9ac7-a05e64329177','Assignment -Unit 2.pdf','08f70b5b-25e3-41a1-9ac7-a05e64329177.pdf',688436,1,'uploaded','2026-09-06 18:24:53'),('104623a2-3d39-48f5-875e-4bcee00ffc1b','Smart Traffic management System Synopsis- - Copy.pdf','104623a2-3d39-48f5-875e-4bcee00ffc1b.pdf',139914,3,'uploaded','2026-09-04 19:28:23'),('19a44427-ccb5-489d-85be-fe90b74b6c0e','OS_File_Management_Answers.pdf','19a44427-ccb5-489d-85be-fe90b74b6c0e.pdf',35715,11,'uploaded','2026-10-24 06:59:47'),('22bd093e-fb89-4f6c-8306-9575a89bd2db','Assignment -Unit 2.pdf','22bd093e-fb89-4f6c-8306-9575a89bd2db.pdf',688436,1,'uploaded','2026-09-06 18:02:31'),('2cebb39e-6ac0-4735-aa49-d72bbc62d3e5','set2023S.pdf','2cebb39e-6ac0-4735-aa49-d72bbc62d3e5.pdf',99310,3,'uploaded','2026-09-13 17:47:55'),('3f65b31f-d240-4427-a755-be1a668a3092','set2022S.pdf','3f65b31f-d240-4427-a755-be1a668a3092.pdf',100132,4,'uploaded','2026-09-13 17:55:40'),('48999d1b-e0a5-4ff1-ab9d-838ad8207974','Regular Not Confirm Student List 30.8.2026.pdf','48999d1b-e0a5-4ff1-ab9d-838ad8207974.pdf',3303306,5,'uploaded','2026-09-06 18:27:34'),('4beb72dc-62f7-4414-9c9a-db9e4fcd43fd','Assignment -Unit 2.pdf','4beb72dc-62f7-4414-9c9a-db9e4fcd43fd.pdf',688436,1,'uploaded','2026-09-06 15:10:06'),('66a88898-4b39-47fa-8b27-be57e17d6fe9','Assignment -Unit 2.pdf','66a88898-4b39-47fa-8b27-be57e17d6fe9.pdf',688436,1,'uploaded','2026-09-05 19:00:17'),('6b187cf2-29ee-47ca-823b-12473069ffd5','Smart Traffic management System Synopsis-.pdf','6b187cf2-29ee-47ca-823b-12473069ffd5.pdf',139914,3,'uploaded','2026-09-05 19:00:17'),('6c89a6f8-02ae-421e-aee9-11892fbce1ad','OSY_Unit4_Memory_Management_Q1-33.pdf','6c89a6f8-02ae-421e-aee9-11892fbce1ad.pdf',53534,12,'uploaded','2026-10-24 07:00:42'),('75e5c5a6-dacc-41e6-9f1d-b378b2d93ace','Smart Traffic management System Synopsis- - Copy.pdf','75e5c5a6-dacc-41e6-9f1d-b378b2d93ace.pdf',139914,3,'uploaded','2026-09-05 19:00:17'),('7ba3d865-4e56-4552-9708-87c71dd6e14a','set2022S.pdf','7ba3d865-4e56-4552-9708-87c71dd6e14a.pdf',100132,4,'uploaded','2026-09-13 14:20:17'),('8a785222-92e5-4211-9137-ef854e4716e2','Assignment -Unit 2.pdf','8a785222-92e5-4211-9137-ef854e4716e2.pdf',688436,1,'uploaded','2026-09-05 18:58:57'),('8b178e4f-2561-4226-af92-56338c3a2fb7','OSY_Unit4_Memory_Management_Q1-33.pdf','8b178e4f-2561-4226-af92-56338c3a2fb7.pdf',53534,12,'uploaded','2026-10-24 07:07:50'),('a6a22055-eeb5-4165-9d69-a4ad92e88465','Assignment -Unit 2.pdf','a6a22055-eeb5-4165-9d69-a4ad92e88465.pdf',688436,1,'uploaded','2026-09-06 18:22:39'),('b66f6d47-1249-4b13-804c-b6a69b06840d','Assignment -Unit 2.pdf','b66f6d47-1249-4b13-804c-b6a69b06840d.pdf',688436,1,'uploaded','2026-09-06 18:21:49'),('be83c2a1-f1a9-4250-a441-b57e852ce8ea','set2022S.pdf','be83c2a1-f1a9-4250-a441-b57e852ce8ea.pdf',100132,4,'uploaded','2026-09-13 14:06:30'),('c13cc567-4c23-4b02-9f6e-dcdbd684a350','OSY_Unit4_Memory_Management_Q1-33.pdf','c13cc567-4c23-4b02-9f6e-dcdbd684a350.pdf',53534,12,'uploaded','2026-10-24 07:09:04'),('e1920910-bfda-460d-a193-a856e191f7a2','FINAL QUESTION BANK.pdf','e1920910-bfda-460d-a193-a856e191f7a2.pdf',73929,1,'uploaded','2026-09-05 19:14:50'),('e98e2423-050a-4963-984d-98b8d5eaf868','3f65b31f-d240-4427-a755-be1a668a3092.pdf','e98e2423-050a-4963-984d-98b8d5eaf868.pdf',100132,4,'uploaded','2026-09-13 18:04:52'),('ec9389f0-df05-43e7-ad38-2085f7fa931e','Assignment -Unit 2.pdf','ec9389f0-df05-43e7-ad38-2085f7fa931e.pdf',688436,1,'uploaded','2026-09-04 19:28:23');
/*!40000 ALTER TABLE `files` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-10-24 13:34:14
